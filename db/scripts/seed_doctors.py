import asyncio

from sqlalchemy import select

from db.config import DATABASE_URL
from db.connection import create_engine, create_session_factory
from db.models import Doctor


DOCTORS = [
    {
        "name": "Dr. Ananya Rao",
        "specialty": "Cardiology",
        "bio": "Specialist in preventive cardiology and heart health.",
    },
    {
        "name": "Dr. Vikram Nair",
        "specialty": "Cardiology",
        "bio": "Cardiologist focused on cardiac diagnostics and treatment.",
    },
    {
        "name": "Dr. Meera Iyer",
        "specialty": "Dermatology",
        "bio": "Dermatologist specializing in medical and clinical skin care.",
    },
    {
        "name": "Dr. Arjun Menon",
        "specialty": "Neurology",
        "bio": "Neurologist specializing in neurological disorders and treatment.",
    },
    {
        "name": "Dr. Priya Shah",
        "specialty": "Pediatrics",
        "bio": "Pediatrician providing comprehensive care for children.",
    },
    {
        "name": "Dr. Rahul Verma",
        "specialty": "Orthopedics",
        "bio": "Orthopedic specialist focused on musculoskeletal conditions.",
    },
]


async def seed_doctors() -> None:
    engine = create_engine(DATABASE_URL)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        for doctor_data in DOCTORS:
            result = await session.execute(
                select(Doctor).where(Doctor.name == doctor_data["name"])
            )

            if result.scalar_one_or_none() is None:
                session.add(Doctor(**doctor_data))
                print(f"Created: {doctor_data['name']}")
            else:
                print(f"Already exists: {doctor_data['name']}")

        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_doctors())
