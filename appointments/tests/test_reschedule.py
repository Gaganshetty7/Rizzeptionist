"""
Integration tests for reschedule_appointment.

Acceptance criteria covered:
  - Successful reschedule → appointment moves, old slot released, new slot booked
  - Reschedule to already-booked slot → SLOT_UNAVAILABLE, original unchanged
  - Reschedule to a past slot → SLOT_IN_PAST, original unchanged
  - Nonexistent appointment → APPOINTMENT_NOT_FOUND
  - Already-cancelled appointment → APPOINTMENT_ALREADY_CANCELLED, slot unchanged
"""

from datetime import datetime, timedelta, timezone

import pytest

from appointments import reschedule_appointment
from appointments.errors import ErrorCode
from db.models import Appointment, Doctor, DoctorSlot, Patient

from tests.conftest import db_session_factory


# ──────────────────────────── helpers ────────────────────────────


async def _create_doctor(session, name="Dr. Resched", specialty="General Medicine"):
    doctor = Doctor(name=name, specialty=specialty, active=True)
    session.add(doctor)
    await session.flush()
    return doctor


async def _create_patient(session, phone):
    patient = Patient(name="Resched Patient", phone_number=phone)
    session.add(patient)
    await session.flush()
    return patient


async def _create_slot(session, doctor_id, *, offset, status="available"):
    now = datetime.now(timezone.utc)
    slot = DoctorSlot(
        doctor_id=doctor_id,
        start_time=now + offset,
        end_time=now + offset + timedelta(minutes=30),
        status=status,
    )
    session.add(slot)
    await session.flush()
    return slot


async def _create_appointment(session, patient_id, doctor_id, slot_id, *, status="scheduled"):
    appt = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        slot_id=slot_id,
        status=status,
    )
    session.add(appt)
    await session.flush()
    return appt


async def _cleanup_ids(*, doctor_ids, patient_ids, slot_ids, appointment_ids):
    """Remove test rows in the correct FK order."""
    async with db_session_factory() as session:
        async with session.begin():
            for aid in appointment_ids:
                await session.execute(
                    Appointment.__table__.delete().where(Appointment.id == aid)
                )
            for sid in slot_ids:
                await session.execute(
                    DoctorSlot.__table__.delete().where(DoctorSlot.id == sid)
                )
            for pid in patient_ids:
                await session.execute(
                    Patient.__table__.delete().where(Patient.id == pid)
                )
            for did in doctor_ids:
                await session.execute(
                    Doctor.__table__.delete().where(Doctor.id == did)
                )


# ──────────────── 1. Successful reschedule ───────────────────────


@pytest.mark.asyncio
async def test_reschedule_appointment_success():
    """
    Reschedule a valid upcoming appointment to another available future slot.

    Verify:
      - appointment now points to the new slot
      - old slot is available
      - new slot is booked
      - returned data shows new slot/doctor details
    """
    async with db_session_factory() as session:
        async with session.begin():
            doctor = await _create_doctor(session)
            patient = await _create_patient(session, "7000000001")

            old_slot = await _create_slot(
                session, doctor.id, offset=timedelta(hours=2), status="booked"
            )
            new_slot = await _create_slot(
                session, doctor.id, offset=timedelta(hours=5), status="available"
            )
            appt = await _create_appointment(
                session, patient.id, doctor.id, old_slot.id
            )

            doctor_id = doctor.id
            patient_id = patient.id
            old_slot_id = old_slot.id
            new_slot_id = new_slot.id
            appt_id = appt.id

    try:
        result = await reschedule_appointment(appt_id, new_slot_id)

        assert result.success is True
        assert result.data["appointment_id"] == appt_id
        assert result.data["doctor_name"] == "Dr. Resched"

        # DB verification
        async with db_session_factory() as session:
            db_appt = await session.get(Appointment, appt_id)
            assert db_appt.slot_id == new_slot_id
            assert db_appt.doctor_id == doctor_id

            db_old_slot = await session.get(DoctorSlot, old_slot_id)
            assert db_old_slot.status == "available"

            db_new_slot = await session.get(DoctorSlot, new_slot_id)
            assert db_new_slot.status == "booked"

    finally:
        await _cleanup_ids(
            doctor_ids=[doctor_id],
            patient_ids=[patient_id],
            slot_ids=[old_slot_id, new_slot_id],
            appointment_ids=[appt_id],
        )


# ──────── 2. Reschedule to an already-booked slot ───────────────


@pytest.mark.asyncio
async def test_reschedule_to_booked_slot_returns_slot_unavailable():
    """
    Reschedule to a slot that is already booked.

    This is the most important test: it proves the old slot is NOT
    released when the new slot cannot be claimed.
    """
    async with db_session_factory() as session:
        async with session.begin():
            doctor = await _create_doctor(session, name="Dr. BookedSlot")
            patient = await _create_patient(session, "7000000002")

            old_slot = await _create_slot(
                session, doctor.id, offset=timedelta(hours=2), status="booked"
            )
            booked_slot = await _create_slot(
                session, doctor.id, offset=timedelta(hours=5), status="booked"
            )
            appt = await _create_appointment(
                session, patient.id, doctor.id, old_slot.id
            )

            doctor_id = doctor.id
            patient_id = patient.id
            old_slot_id = old_slot.id
            booked_slot_id = booked_slot.id
            appt_id = appt.id

    try:
        result = await reschedule_appointment(appt_id, booked_slot_id)

        assert result.success is False
        assert result.error_code == ErrorCode.SLOT_UNAVAILABLE

        # Original appointment and slot must remain unchanged.
        async with db_session_factory() as session:
            db_appt = await session.get(Appointment, appt_id)
            assert db_appt.slot_id == old_slot_id
            assert db_appt.status == "scheduled"

            db_old_slot = await session.get(DoctorSlot, old_slot_id)
            assert db_old_slot.status == "booked"

    finally:
        await _cleanup_ids(
            doctor_ids=[doctor_id],
            patient_ids=[patient_id],
            slot_ids=[old_slot_id, booked_slot_id],
            appointment_ids=[appt_id],
        )


# ──────────── 3. Reschedule to a past slot ───────────────────────


@pytest.mark.asyncio
async def test_reschedule_to_past_slot_returns_slot_in_past():
    """
    Reschedule to a slot whose start_time is already in the past.

    Verify SLOT_IN_PAST and that the original appointment/slot are unchanged.
    """
    async with db_session_factory() as session:
        async with session.begin():
            doctor = await _create_doctor(session, name="Dr. PastSlot")
            patient = await _create_patient(session, "7000000003")

            old_slot = await _create_slot(
                session, doctor.id, offset=timedelta(hours=2), status="booked"
            )
            past_slot = await _create_slot(
                session, doctor.id, offset=timedelta(hours=-3), status="available"
            )
            appt = await _create_appointment(
                session, patient.id, doctor.id, old_slot.id
            )

            doctor_id = doctor.id
            patient_id = patient.id
            old_slot_id = old_slot.id
            past_slot_id = past_slot.id
            appt_id = appt.id

    try:
        result = await reschedule_appointment(appt_id, past_slot_id)

        assert result.success is False
        assert result.error_code == ErrorCode.SLOT_IN_PAST

        # Original appointment and slot must remain unchanged.
        async with db_session_factory() as session:
            db_appt = await session.get(Appointment, appt_id)
            assert db_appt.slot_id == old_slot_id
            assert db_appt.status == "scheduled"

            db_old_slot = await session.get(DoctorSlot, old_slot_id)
            assert db_old_slot.status == "booked"

    finally:
        await _cleanup_ids(
            doctor_ids=[doctor_id],
            patient_ids=[patient_id],
            slot_ids=[old_slot_id, past_slot_id],
            appointment_ids=[appt_id],
        )


# ──────────── 4. Nonexistent appointment ─────────────────────────


@pytest.mark.asyncio
async def test_reschedule_nonexistent_appointment():
    """Rescheduling a nonexistent appointment must return APPOINTMENT_NOT_FOUND."""
    result = await reschedule_appointment(999999, 1)

    assert result.success is False
    assert result.data is None
    assert result.error_code == ErrorCode.APPOINTMENT_NOT_FOUND


# ──────────── 5. Already-cancelled appointment ───────────────────


@pytest.mark.asyncio
async def test_reschedule_cancelled_appointment():
    """
    Rescheduling a cancelled appointment must return APPOINTMENT_ALREADY_CANCELLED.

    The slot must remain available and nothing should change.
    """
    async with db_session_factory() as session:
        async with session.begin():
            doctor = await _create_doctor(session, name="Dr. Cancelled")
            patient = await _create_patient(session, "7000000005")

            # The slot is available because the appointment was already cancelled.
            old_slot = await _create_slot(
                session, doctor.id, offset=timedelta(hours=2), status="available"
            )
            new_slot = await _create_slot(
                session, doctor.id, offset=timedelta(hours=6), status="available"
            )
            appt = await _create_appointment(
                session, patient.id, doctor.id, old_slot.id, status="cancelled"
            )

            doctor_id = doctor.id
            patient_id = patient.id
            old_slot_id = old_slot.id
            new_slot_id = new_slot.id
            appt_id = appt.id

    try:
        result = await reschedule_appointment(appt_id, new_slot_id)

        assert result.success is False
        assert result.error_code == ErrorCode.APPOINTMENT_ALREADY_CANCELLED

        # Slots must remain unchanged.
        async with db_session_factory() as session:
            db_old_slot = await session.get(DoctorSlot, old_slot_id)
            assert db_old_slot.status == "available"

            db_new_slot = await session.get(DoctorSlot, new_slot_id)
            assert db_new_slot.status == "available"

    finally:
        await _cleanup_ids(
            doctor_ids=[doctor_id],
            patient_ids=[patient_id],
            slot_ids=[old_slot_id, new_slot_id],
            appointment_ids=[appt_id],
        )

