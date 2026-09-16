from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Patient


async def get_or_create_patient(
    session: AsyncSession,
    phone_number: str,
    name: str,
) -> Patient:
    # Try to insert a new patient. If a patient with the same phone number already exists, do nothing.
    # Safety for concurrent requests
    stmt = (
        insert(Patient)
        .values(
            phone_number=phone_number,
            name=name,
        )
        .on_conflict_do_nothing(
            index_elements=[Patient.phone_number],
        )
        .returning(Patient)
    )

    result = await session.execute(stmt)
    patient = result.scalar_one_or_none()

    if patient is not None:
        await session.commit()
        return patient

    # Another request already created this patient.
    await session.rollback()

    result = await session.execute(
        select(Patient).where(Patient.phone_number == phone_number)
    )

    return result.scalar_one()
