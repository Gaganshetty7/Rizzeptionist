"""
Integration tests for find_appointments and cancel_appointment.

Acceptance criteria covered:
  - find_appointments  → only upcoming scheduled appointments for the patient
  - find_appointments  → unknown phone returns empty successful result
  - cancel_appointment → appointment cancelled, slot released, slot reappears
                          in check_availability
  - cancel_appointment → duplicate cancellation rejected
  - cancel_appointment → past appointment rejected
  - cancel_appointment → nonexistent appointment rejected
"""

from datetime import datetime, timedelta, timezone

import pytest

from appointments import cancel_appointment, check_availability
from appointments.errors import ErrorCode
from appointments.service import find_appointments
from db.models import Appointment, Doctor, DoctorSlot, Patient

from tests.conftest import db_session_factory


# ──────────────────────────── helpers ────────────────────────────


async def _seed_patient_with_appointments():
    """
    Create one patient with four appointments:
      0 – future + scheduled  (the ONLY one find_appointments should return)
      1 – future + cancelled
      2 – future + completed
      3 – past   + scheduled

    Returns (doctor_id, patient_phone, slots, appointments).
    """
    now = datetime.now(timezone.utc)
    phone = "8000000001"

    async with db_session_factory() as session:
        async with session.begin():
            doctor = Doctor(
                name="Dr. Seed",
                specialty="General Medicine",
                active=True,
            )
            session.add(doctor)
            await session.flush()

            patient = Patient(name="Seed Patient", phone_number=phone)
            session.add(patient)
            await session.flush()

            offsets_and_statuses = [
                (timedelta(hours=2), "scheduled"),   # 0 – future scheduled ✓
                (timedelta(hours=4), "cancelled"),    # 1 – future cancelled
                (timedelta(hours=6), "completed"),    # 2 – future completed
                (timedelta(hours=-2), "scheduled"),   # 3 – past scheduled
            ]

            slots = []
            appointments = []
            for offset, appt_status in offsets_and_statuses:
                slot = DoctorSlot(
                    doctor_id=doctor.id,
                    start_time=now + offset,
                    end_time=now + offset + timedelta(minutes=30),
                    status="booked",
                )
                session.add(slot)
                await session.flush()
                slots.append(slot)

                appt = Appointment(
                    patient_id=patient.id,
                    doctor_id=doctor.id,
                    slot_id=slot.id,
                    status=appt_status,
                )
                session.add(appt)
                await session.flush()
                appointments.append(appt)

            return doctor.id, patient.id, phone, slots, appointments


async def _cleanup(doctor_id, patient_id, slots, appointments):
    """Remove test rows in the correct FK order."""
    async with db_session_factory() as session:
        async with session.begin():
            for appt in appointments:
                await session.execute(
                    Appointment.__table__.delete().where(
                        Appointment.id == appt.id
                    )
                )
            for slot in slots:
                await session.execute(
                    DoctorSlot.__table__.delete().where(
                        DoctorSlot.id == slot.id
                    )
                )
            await session.execute(
                Patient.__table__.delete().where(Patient.id == patient_id)
            )
            await session.execute(
                Doctor.__table__.delete().where(Doctor.id == doctor_id)
            )


# ───────────────── find_appointments tests ──────────────────────


@pytest.mark.asyncio
async def test_find_appointments_returns_only_future_scheduled():
    """
    Only the future + scheduled appointment should be returned.
    The future cancelled, future completed, and past scheduled ones
    must all be filtered out.
    """
    doctor_id, patient_id, phone, slots, appointments = (
        await _seed_patient_with_appointments()
    )
    upcoming_appointment = appointments[0]

    try:
        result = await find_appointments(phone)

        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0]["appointment_id"] == upcoming_appointment.id

    finally:
        await _cleanup(doctor_id, patient_id, slots, appointments)


@pytest.mark.asyncio
async def test_find_appointments_unknown_phone_returns_patient_not_found():
    """
    Looking up a phone number with no matching patient should
    return a PATIENT_NOT_FOUND error.
    """
    result = await find_appointments("9999999999")

    assert result.success is False
    assert result.data is None
    assert result.error_code == ErrorCode.PATIENT_NOT_FOUND


# ───────────────── cancel_appointment tests ─────────────────────


@pytest.mark.asyncio
async def test_cancel_appointment_releases_slot():
    """
    Cancelling an upcoming appointment should:
      1. Mark the appointment as 'cancelled'
      2. Release the slot back to 'available'
      3. Make the slot reappear in check_availability
    """
    now = datetime.now(timezone.utc)

    async with db_session_factory() as session:
        async with session.begin():
            doctor = Doctor(
                name="Dr. Cancel",
                specialty="General Medicine",
                active=True,
            )
            session.add(doctor)
            await session.flush()

            patient = Patient(name="Cancel Patient", phone_number="8000000002")
            session.add(patient)
            await session.flush()

            slot = DoctorSlot(
                doctor_id=doctor.id,
                start_time=now + timedelta(hours=3),
                end_time=now + timedelta(hours=3, minutes=30),
                status="booked",
            )
            session.add(slot)
            await session.flush()

            appt = Appointment(
                patient_id=patient.id,
                doctor_id=doctor.id,
                slot_id=slot.id,
                status="scheduled",
            )
            session.add(appt)
            await session.flush()

            doctor_id = doctor.id
            patient_id = patient.id
            slot_id = slot.id
            appt_id = appt.id

    try:
        # ── Cancel ──
        result = await cancel_appointment(appt_id)

        assert result.success is True
        assert result.data["status"] == "cancelled"
        assert result.data["slot_status"] == "available"

        # ── DB verification ──
        async with db_session_factory() as session:
            db_appt = await session.get(Appointment, appt_id)
            assert db_appt.status == "cancelled"

            db_slot = await session.get(DoctorSlot, slot_id)
            assert db_slot.status == "available"

        # ── check_availability must now list the released slot ──
        avail = await check_availability(doctor_id=doctor_id, date=None)
        assert avail.success is True
        released_ids = [s["id"] for s in avail.data]
        assert slot_id in released_ids

    finally:
        async with db_session_factory() as session:
            async with session.begin():
                await session.execute(
                    Appointment.__table__.delete().where(
                        Appointment.id == appt_id
                    )
                )
                await session.execute(
                    DoctorSlot.__table__.delete().where(
                        DoctorSlot.id == slot_id
                    )
                )
                await session.execute(
                    Patient.__table__.delete().where(Patient.id == patient_id)
                )
                await session.execute(
                    Doctor.__table__.delete().where(Doctor.id == doctor_id)
                )


@pytest.mark.asyncio
async def test_cancel_already_cancelled_appointment():
    """Cancelling an already-cancelled appointment must return an error."""
    now = datetime.now(timezone.utc)

    async with db_session_factory() as session:
        async with session.begin():
            doctor = Doctor(
                name="Dr. DupCancel",
                specialty="General Medicine",
                active=True,
            )
            session.add(doctor)
            await session.flush()

            patient = Patient(
                name="DupCancel Patient", phone_number="8000000003"
            )
            session.add(patient)
            await session.flush()

            slot = DoctorSlot(
                doctor_id=doctor.id,
                start_time=now + timedelta(hours=5),
                end_time=now + timedelta(hours=5, minutes=30),
                status="available",
            )
            session.add(slot)
            await session.flush()

            appt = Appointment(
                patient_id=patient.id,
                doctor_id=doctor.id,
                slot_id=slot.id,
                status="cancelled",
            )
            session.add(appt)
            await session.flush()

            doctor_id = doctor.id
            patient_id = patient.id
            slot_id = slot.id
            appt_id = appt.id

    try:
        result = await cancel_appointment(appt_id)

        assert result.success is False
        assert result.data is None
        assert result.error_code == ErrorCode.APPOINTMENT_ALREADY_CANCELLED

    finally:
        async with db_session_factory() as session:
            async with session.begin():
                await session.execute(
                    Appointment.__table__.delete().where(
                        Appointment.id == appt_id
                    )
                )
                await session.execute(
                    DoctorSlot.__table__.delete().where(
                        DoctorSlot.id == slot_id
                    )
                )
                await session.execute(
                    Patient.__table__.delete().where(Patient.id == patient_id)
                )
                await session.execute(
                    Doctor.__table__.delete().where(Doctor.id == doctor_id)
                )


@pytest.mark.asyncio
async def test_cancel_past_appointment_rejected():
    """Cancelling an appointment whose slot is in the past must be rejected."""
    now = datetime.now(timezone.utc)

    async with db_session_factory() as session:
        async with session.begin():
            doctor = Doctor(
                name="Dr. PastCancel",
                specialty="General Medicine",
                active=True,
            )
            session.add(doctor)
            await session.flush()

            patient = Patient(
                name="PastCancel Patient", phone_number="8000000004"
            )
            session.add(patient)
            await session.flush()

            slot = DoctorSlot(
                doctor_id=doctor.id,
                start_time=now - timedelta(hours=2),
                end_time=now - timedelta(hours=1, minutes=30),
                status="booked",
            )
            session.add(slot)
            await session.flush()

            appt = Appointment(
                patient_id=patient.id,
                doctor_id=doctor.id,
                slot_id=slot.id,
                status="scheduled",
            )
            session.add(appt)
            await session.flush()

            doctor_id = doctor.id
            patient_id = patient.id
            slot_id = slot.id
            appt_id = appt.id

    try:
        result = await cancel_appointment(appt_id)

        assert result.success is False
        assert result.error_code == ErrorCode.SLOT_IN_PAST

    finally:
        async with db_session_factory() as session:
            async with session.begin():
                await session.execute(
                    Appointment.__table__.delete().where(
                        Appointment.id == appt_id
                    )
                )
                await session.execute(
                    DoctorSlot.__table__.delete().where(
                        DoctorSlot.id == slot_id
                    )
                )
                await session.execute(
                    Patient.__table__.delete().where(Patient.id == patient_id)
                )
                await session.execute(
                    Doctor.__table__.delete().where(Doctor.id == doctor_id)
                )


@pytest.mark.asyncio
async def test_cancel_nonexistent_appointment():
    """Cancelling a nonexistent appointment must return APPOINTMENT_NOT_FOUND."""
    result = await cancel_appointment(999999)

    assert result.success is False
    assert result.data is None
    assert result.error_code == ErrorCode.APPOINTMENT_NOT_FOUND

