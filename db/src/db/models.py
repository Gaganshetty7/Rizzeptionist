from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement = True,
    )

    name: Mapped[str] = mapped_column(
        String,
        nullable = False,
    )

    specialty: Mapped[str] = mapped_column(
        String,
        nullable = False,
    )

    bio: Mapped[str | None] = mapped_column(
        Text,
        nullable = True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable = False,
        server_default = text("true")
    )

    __table_args__ = (
        Index(
            "ix_doctors_specialty",
            "specialty"
        ),
    )


class DoctorSlot(Base):
    __tablename__ = "doctor_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    doctor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("doctors.id"),
        nullable=False,
    )

    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="available",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('available', 'booked')",
            name="ck_doctor_slots_status",
        ),
        Index(
            "ix_doctor_slots_doctor_id_start_time",
            "doctor_id",
            "start_time",
        ),
    )



class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    phone_number: Mapped[str] = mapped_column(
        String,
        nullable=False,
        unique=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
    )

    doctor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("doctors.id"),
        nullable=False,
        index=True,
    )

    slot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("doctor_slots.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="scheduled",
        server_default="scheduled",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled', 'cancelled', 'completed')",
            name="ck_appointments_status",
        ),
    )

