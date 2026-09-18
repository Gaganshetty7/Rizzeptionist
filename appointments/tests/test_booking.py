"""
Concurrency & integration tests for appointment booking.

Key design:
  - Each call to book_appointment() opens its own DB session via the
    service module's _session_factory.  The two concurrent bookings in
    the race test therefore contend through real PostgreSQL row locks.
  - db_session_factory (from conftest) is used only for test
    setup/teardown/verification — never for the bookings themselves.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from appointments import book_appointment
from appointments.errors import ErrorCode
from db.models import Appointment, Doctor, DoctorSlot, Patient

# Re-use the test-only session factory from conftest.
from tests.conftest import db_session_factory


# ──────────────────────────── helpers ────────────────────────────


async def create_test_doctor_and_slot(
    *,
    start_offset: timedelta = timedelta(hours=2),
    end_offset: timedelta = timedelta(hours=2, minutes=30),
    slot_status: str = "available",
):
    """Insert a doctor + slot and return their IDs."""
    async with db_session_factory() as session:
        async with session.begin():
            doctor = Doctor(
                name="Test Doctor",
                specialty="General Medicine",
                active=True,
            )
            session.add(doctor)
            await session.flush()

            slot = DoctorSlot(
                doctor_id=doctor.id,
                start_time=datetime.now(timezone.utc) + start_offset,
                end_time=datetime.now(timezone.utc) + end_offset,
                status=slot_status,
            )
            session.add(slot)
            await session.flush()

            return doctor.id, slot.id


async def delete_test_data(doctor_id: int, slot_id: int):
    """Remove test rows in the correct FK order."""
    async with db_session_factory() as session:
        async with session.begin():
            await session.execute(
                Appointment.__table__.delete().where(
                    Appointment.slot_id == slot_id
                )
            )
            await session.execute(
                DoctorSlot.__table__.delete().where(DoctorSlot.id == slot_id)
            )
            await session.execute(
                Doctor.__table__.delete().where(Doctor.id == doctor_id)
            )


# ─────────────────────── concurrency race test ───────────────────────


@pytest.mark.asyncio
async def test_two_concurrent_bookings_only_one_succeeds():
    """
    Fire two book_appointment() calls for the *same* slot concurrently.
    Exactly one must win; the other must get SLOT_UNAVAILABLE.
    """
    doctor_id, slot_id = await create_test_doctor_and_slot()

    try:
        result_1, result_2 = await asyncio.gather(
            book_appointment(
                slot_id=slot_id,
                patient_name="Patient One",
                patient_phone="9000000001",
            ),
            book_appointment(
                slot_id=slot_id,
                patient_name="Patient Two",
                patient_phone="9000000002",
            ),
        )

        results = [result_1, result_2]
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]

        # Exactly one booking must succeed.
        assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
        assert len(failures) == 1, f"Expected 1 failure, got {len(failures)}"

        # The loser must get the clean contract error.
        assert failures[0].error_code == ErrorCode.SLOT_UNAVAILABLE

        # ── DB verification ──
        async with db_session_factory() as session:
            slot = await session.get(DoctorSlot, slot_id)
            assert slot is not None
            assert slot.status == "booked"

            appointment_count = await session.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(Appointment.slot_id == slot_id)
            )
            assert appointment_count == 1

    finally:
        await delete_test_data(doctor_id, slot_id)


# ──────────────── sequential double-booking test ─────────────────


@pytest.mark.asyncio
async def test_booking_already_booked_slot_returns_slot_unavailable():
    """Book a slot, then try to book it again — second attempt must fail."""
    doctor_id, slot_id = await create_test_doctor_and_slot()

    try:
        first = await book_appointment(
            slot_id=slot_id,
            patient_name="Patient One",
            patient_phone="9000000011",
        )
        second = await book_appointment(
            slot_id=slot_id,
            patient_name="Patient Two",
            patient_phone="9000000012",
        )

        assert first.success is True
        assert second.success is False
        assert second.error_code == ErrorCode.SLOT_UNAVAILABLE

    finally:
        await delete_test_data(doctor_id, slot_id)


# ──────────────────── past-slot rejection test ───────────────────


@pytest.mark.asyncio
async def test_booking_past_slot_is_rejected():
    """A slot whose start_time is in the past must be rejected."""
    async with db_session_factory() as session:
        async with session.begin():
            doctor = Doctor(
                name="Past Slot Doctor",
                specialty="General Medicine",
                active=True,
            )
            session.add(doctor)
            await session.flush()

            slot = DoctorSlot(
                doctor_id=doctor.id,
                start_time=datetime.now(timezone.utc) - timedelta(hours=1),
                end_time=datetime.now(timezone.utc) - timedelta(minutes=30),
                status="available",
            )
            session.add(slot)
            await session.flush()

            doctor_id = doctor.id
            slot_id = slot.id

    try:
        result = await book_appointment(
            slot_id=slot_id,
            patient_name="Past Patient",
            patient_phone="9000000021",
        )

        assert result.success is False
        assert result.error_code == ErrorCode.SLOT_IN_PAST

        # Slot must remain available and no appointment created.
        async with db_session_factory() as session:
            slot = await session.get(DoctorSlot, slot_id)
            assert slot.status == "available"

            appointment_count = await session.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(Appointment.slot_id == slot_id)
            )
            assert appointment_count == 0

    finally:
        await delete_test_data(doctor_id, slot_id)


# ────────────── rollback-safety / no partial state test ──────────────


@pytest.mark.asyncio
async def test_failed_booking_rolls_back_slot_change():
    """
    Acceptance criterion: a failed booking leaves no partial state behind.

    Setup:
      - Create a doctor + slot (status = 'available').
      - Directly insert a *conflicting* appointment row for that slot,
        so the unique constraint on appointments.slot_id is already occupied.

    When book_appointment() runs it will:
      1. SELECT ... FOR UPDATE  →  slot.status == 'available'  →  passes
      2. slot.status = 'booked'              (in-memory, within txn)
      3. session.add(appointment) + flush()   →  IntegrityError (slot_id unique)
      4. Transaction rolls back

    We then verify:
      - slot.status is still 'available'     (mutation rolled back)
      - Only the pre-inserted appointment exists (no partial row)
    """
    doctor_id, slot_id = await create_test_doctor_and_slot()

    # Pre-insert a conflicting appointment directly — slot stays 'available'
    # but the unique constraint on appointments.slot_id is now occupied.
    async with db_session_factory() as session:
        async with session.begin():
            # We need a patient to attach the dummy appointment to.
            from db.repositories.patients import get_or_create_patient

            patient = await get_or_create_patient(
                session=session,
                phone_number="9000000099",
                name="Conflict Patient",
            )

            # Get the doctor_id for the FK
            slot_row = await session.get(DoctorSlot, slot_id)

            dummy_appointment = Appointment(
                patient_id=patient.id,
                doctor_id=slot_row.doctor_id,
                slot_id=slot_id,
                status="scheduled",
            )
            session.add(dummy_appointment)
            await session.flush()

            dummy_appointment_id = dummy_appointment.id

    try:
        # book_appointment() sees slot.status == 'available', sets it to
        # 'booked', then tries to INSERT an appointment → IntegrityError
        # on the slot_id unique constraint → entire txn rolls back.
        result = await book_appointment(
            slot_id=slot_id,
            patient_name="Rollback Patient",
            patient_phone="9000000041",
        )

        assert result.success is False
        assert result.error_code == ErrorCode.SLOT_UNAVAILABLE

        # ── DB verification: no partial state ──
        async with db_session_factory() as session:
            # Slot must still be 'available' — the 'booked' mutation rolled back.
            slot = await session.get(DoctorSlot, slot_id)
            assert slot.status == "available", (
                f"Expected slot to revert to 'available', got '{slot.status}'"
            )

            # Only the pre-inserted dummy appointment exists.
            appointment_count = await session.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(Appointment.slot_id == slot_id)
            )
            assert appointment_count == 1, (
                f"Expected exactly 1 (dummy) appointment, got {appointment_count}"
            )

    finally:
        # Clean up the dummy appointment + test data.
        async with db_session_factory() as session:
            async with session.begin():
                await session.execute(
                    Appointment.__table__.delete().where(
                        Appointment.id == dummy_appointment_id
                    )
                )
        await delete_test_data(doctor_id, slot_id)
