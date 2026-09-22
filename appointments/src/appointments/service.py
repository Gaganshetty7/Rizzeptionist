from datetime import date, datetime, time, timedelta, timezone

from appointments.errors import ErrorCode
from db.models import Appointment, Patient
from db.repositories.patients import get_or_create_patient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db import (
    DATABASE_URL,
    Doctor,
    DoctorSlot,
    create_engine,
    create_session_factory,
)
from appointments import AppointmentResult

# Constants
MAX_AVAILABLE_SLOTS = 5

# Create a database engine and session factory
_engine = create_engine(DATABASE_URL)
_session_factory = create_session_factory(_engine)


# Service functions

async def find_doctors(
    name: str | None,
    specialty: str | None,
) -> AppointmentResult:
    """
    Find active doctors matching the provided name and/or specialty.
    """
    async with _session_factory() as session:
        query = select(Doctor).where(Doctor.active.is_(True))

        # Name filtering with case-insensitive regex matching
        if name and name.strip():
            query = query.where(
                Doctor.name.op("~*")(
                    rf"(^|[^[:alnum:]]){name.strip()}([^[:alnum:]]|$)"
                )
            )

        # Specialty filtering
        if specialty and specialty.strip():
            query = query.where(
                Doctor.specialty.ilike(f"%{specialty.strip()}%")
            )

        # Order by doctor name
        query = query.order_by(Doctor.name)

        result = await session.execute(query)
        doctors = result.scalars().all()

        data = [
            {
                "id": doctor.id,
                "name": doctor.name,
                "specialty": doctor.specialty,
                "bio": doctor.bio,
            }
            for doctor in doctors
        ]

        return AppointmentResult.ok(
            data,
            "Doctors found successfully.",
        )


async def check_availability(
    doctor_id: int,
    date: date | None,
) -> AppointmentResult:
    """
    Return available future slots for a doctor.
    """
    now = datetime.now(timezone.utc)

    async with _session_factory() as session:
        query = (
            select(DoctorSlot)
            .where(
                DoctorSlot.doctor_id == doctor_id,
                DoctorSlot.status == "available",
                DoctorSlot.start_time > now,
            )
            .order_by(DoctorSlot.start_time)
            .limit(MAX_AVAILABLE_SLOTS)
        )

        # To check for slots within the requested date
        if date is not None:
            # Converting simple date to datetime object so that its easy to search in db
            start_of_day = datetime.combine(
                date,
                time.min, # basically min of time 00:00:00
                tzinfo=timezone.utc, # tagging it as utc to correct time offset +00:00
            )

            start_of_next_day = start_of_day + timedelta(days=1)

            query = query.where(
                DoctorSlot.start_time >= start_of_day,
                DoctorSlot.end_time <= start_of_next_day,
            )

        result = await session.execute(query)
        slots = result.scalars().all()

        data = [
            {
                "id": slot.id,
                "start_time": slot.start_time,
                "end_time": slot.end_time,
            }
            for slot in slots
        ]

        return AppointmentResult.ok(
            data,
            "Available slots found successfully.",
        )
    

async def book_appointment(
    slot_id: int,
    patient_name: str,
    patient_phone: str,
) -> AppointmentResult:
    """
    Book an appointment after validating the requested slot.

    The slot is locked for the duration of the transaction so concurrent
    booking attempts cannot both reserve the same slot.
    """
    now = datetime.now(timezone.utc)

    try:
        async with _session_factory() as session:
            async with session.begin():

                # Lock the slot row so concurrent bookings for the same slot are serialized.
                result = await session.execute(
                    select(DoctorSlot)
                    .where(DoctorSlot.id == slot_id)
                    .with_for_update()
                )
                slot = result.scalar_one_or_none()

                # Slot doesn't exist
                if slot is None:
                    return AppointmentResult.failure(
                        ErrorCode.SLOT_UNAVAILABLE,
                        "The requested slot is unavailable",
                    )

                # Slot has been already booked
                if slot.status != "available":
                    return AppointmentResult.failure(
                        ErrorCode.SLOT_UNAVAILABLE,
                        "The requested slot is unavailable",
                    )

                # SLot has already passed
                if slot.start_time <= now:
                    return AppointmentResult.failure(
                        ErrorCode.SLOT_IN_PAST,
                        "The requested appointment slot is in the past.",
                    )

                # Fetch doctor details required for the confirmation response.
                doctor_result = await session.execute(
                    select(Doctor)
                    .where(Doctor.id == slot.doctor_id)
                )
                doctor = doctor_result.scalar_one_or_none()

                if doctor is None:
                    return AppointmentResult.failure(
                        ErrorCode.DOCTOR_NOT_FOUND,
                        "The doctor for this slot could not be found.",
                    )

                # Create patient if not exists using the repository method
                patient = await get_or_create_patient(
                    session=session,
                    phone_number=patient_phone,
                    name=patient_name
                )

                # Reserve slot
                slot.status = "booked"

                # Create the appointment in the same transaction.
                appointment = Appointment(
                    patient_id=patient.id,
                    doctor_id=doctor.id,
                    slot_id=slot.id,
                    status="scheduled",
                )
                session.add(appointment)

                # Force INSERT now so the appointment ID is available and any unique-constraint race is detected before commit.
                # Basically, SQLAlchemy buffers all operations locally and sends them to PostgreSQL in a batch at the end of the transaction
                # Hence, When you manually insert a session.flush() in between, you force that batch to leave your application and go to PostgreSQL early, without closing the transaction.
                # This is necessary because we need the appointment ID, which is generated centrally by PostgreSQL's global sequence tracker
                await session.flush()

                data = {
                    "appointment_id": appointment.id,
                    "doctor_name": doctor.name,
                    "date": slot.start_time.date().isoformat(),
                    "start_time": slot.start_time.isoformat(),
                    "end_time": slot.end_time.isoformat(),
                }

                return AppointmentResult.ok(
                    data,
                    "Appointment booked successfully.",
                )
    except IntegrityError:
        # The unique constraint on appointments.slot_id is the final concurrency safety net.
        # Any such race causes the whole transaction to roll back, leaving the slot available and no orphaned appointment.
        return AppointmentResult.failure(
            ErrorCode.SLOT_UNAVAILABLE,
            "The requested slot is unavailable.",
        )


async def find_appointments(
    patient_phone: str,
) -> AppointmentResult:
    # Find all upcoming scheduled appointments for a patient using their phone number.

    now = datetime.now(timezone.utc)

    async with _session_factory() as session:
        # Check that the patient exists first.
        patient_result = await session.execute(
            select(Patient).where(
                Patient.phone_number == patient_phone.strip()
            )
        )
        patient = patient_result.scalar_one_or_none()

        if patient is None:
            return AppointmentResult.failure(
                ErrorCode.PATIENT_NOT_FOUND,
                "No patient found with that phone number.",
            )

        result = await session.execute(
            select(
                Appointment,
                Doctor,
                DoctorSlot,
            )
            .join(Patient, Patient.id == Appointment.patient_id)
            .join(Doctor, Doctor.id == Appointment.doctor_id)
            .join(DoctorSlot, DoctorSlot.id == Appointment.slot_id)
            .where(
                Patient.phone_number == patient_phone.strip(),
                Appointment.status == "scheduled",
                DoctorSlot.start_time > now,
            )
            .order_by(DoctorSlot.start_time)
        )

        rows = result.all()

        data = [
            {
                "appointment_id": appointment.id,
                "patient_id": appointment.patient_id,
                "doctor_id": appointment.doctor_id,
                "doctor_name": doctor.name,
                "specialty": doctor.specialty,
                "slot_id": slot.id,
                "start_time": slot.start_time,
                "end_time": slot.end_time,
                "status": appointment.status,
            }
            for appointment, doctor, slot in rows
        ]

    return AppointmentResult.ok(
            data,
            "Appointments found successfully.",
        )


async def cancel_appointment(
    appointment_id: int,
) -> AppointmentResult:
    """
    Cancel an existing appointment.
    """
    now = datetime.now(timezone.utc)

    async with _session_factory() as session:
        async with session.begin():
            # Lock the appointment so concurrent operations cannot modify it at the same time.
            
            result = await session.execute(
                select(Appointment)
                .where(Appointment.id == appointment_id)
                .with_for_update()
            )

            appointment = result.scalar_one_or_none()

            if appointment is None:
                return AppointmentResult.failure(
                    ErrorCode.APPOINTMENT_NOT_FOUND,
                    "Appointment not found.",
                )

            if appointment.status == "cancelled":
                return AppointmentResult.failure(
                    ErrorCode.APPOINTMENT_ALREADY_CANCELLED,
                    "Appointment is already cancelled.",
                )

            if appointment.status == "completed":
                return AppointmentResult.failure(
                    ErrorCode.APPOINTMENT_ALREADY_COMPLETED,
                    "Appointment has already been completed.",
                )

            # Lock the slot as well because cancellation changes the slot's availability.
            result = await session.execute(
                select(DoctorSlot)
                .where(DoctorSlot.id == appointment.slot_id)
            )

            slot = result.scalar_one()

            # A scheduled appointment whose slot has already started cannot be cancelled.
            if slot.start_time <= now:
                return AppointmentResult.failure(
                    ErrorCode.SLOT_IN_PAST,
                    "The appointment is already in the past.",
                )

            # Cancel appointment.
            appointment.status = "cancelled"
            # Release slot so it can be booked again.
            slot.status = "available"

            await session.flush()

            data = {
                    "appointment_id": appointment.id,
                    "patient_id": appointment.patient_id,
                    "doctor_id": appointment.doctor_id,
                    "slot_id": slot.id,
                    "start_time": slot.start_time,
                    "end_time": slot.end_time,
                    "status": appointment.status,
                    "slot_status": slot.status,
            }

            return AppointmentResult.ok(
                data,
                "Appointment cancelled successfully.",
            )


async def reschedule_appointment(
    appointment_id: int,
    new_appointment_time,
) -> AppointmentResult:
    """
    Move an existing appointment to a new time slot.
    """
    raise NotImplementedError
