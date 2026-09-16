import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db.config import DATABASE_URL
from db.connection import create_engine, create_session_factory
from db.models import Doctor, DoctorSlot

SLOT_MINUTES = 30
DAYS_AHEAD = 7
START_HOUR = 9
END_HOUR = 17


async def seed_doctor_slots() -> None:
    engine = create_engine(DATABASE_URL)
    session_factory = create_session_factory(engine)

    now = datetime.now(timezone.utc)
    start_date = now.date()

    async with session_factory() as session:
        doctors_result = await session.execute(
            select(Doctor).where(Doctor.active.is_(True))
        )
        doctors = doctors_result.scalars().all()

        for doctor in doctors:
            for day_offset in range(DAYS_AHEAD):
                current_date = start_date + timedelta(days=day_offset)

                # Skip weekends for now.
                # Change this if doctors should have weekend availability.
                if current_date.weekday() >= 5:
                    continue

                slot_start = datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    START_HOUR,
                    0,
                    tzinfo=timezone.utc,
                )

                day_end = datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    END_HOUR,
                    0,
                    tzinfo=timezone.utc,
                )

                while slot_start < day_end:
                    slot_end = slot_start + timedelta(minutes=SLOT_MINUTES)

                    existing_result = await session.execute(
                        select(DoctorSlot.id).where(
                            DoctorSlot.doctor_id == doctor.id,
                            DoctorSlot.start_time == slot_start,
                        )
                    )

                    if existing_result.scalar_one_or_none() is None:
                        session.add(
                            DoctorSlot(
                                doctor_id=doctor.id,
                                start_time=slot_start,
                                end_time=slot_end,
                                status="available",
                            )
                        )

                    slot_start = slot_end

        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_doctor_slots())
