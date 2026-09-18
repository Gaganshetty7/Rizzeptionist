from datetime import date, datetime, time, timedelta, timezone

from appointments.errors import ErrorCode
from db.models import Appointment
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



async def cancel_appointment(
    appointment_id: int,
) -> AppointmentResult:
    """
    Cancel an existing appointment.
    """
    raise NotImplementedError


async def reschedule_appointment(
    appointment_id: int,
    new_appointment_time,
) -> AppointmentResult:
    """
    Move an existing appointment to a new time slot.
    """
    raise NotImplementedError
