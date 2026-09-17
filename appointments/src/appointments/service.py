from datetime import date, datetime, time, timedelta, timezone
from unittest import result

from sqlalchemy import select

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
    doctor_id: int,
    patient_id: int,
    appointment_time,
) -> AppointmentResult:
    """
    Book an appointment after validating the requested slot.
    """
    raise NotImplementedError


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
