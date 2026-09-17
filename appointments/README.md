# Appointments

Standalone appointment business-logic package for Rizzeptionist.

## Purpose

The `appointments` package owns all appointment-related business logic.

The `/server` and `/agent` packages must use this package instead of accessing
appointment database models directly.

Dependency boundary:

    server ──┐
             ├──> appointments ───> db
    agent  ──┘

## Responsibilities

This package will provide functions for:

- Checking appointment availability
- Booking appointments
- Cancelling appointments
- Rescheduling appointments

Database models and database connection/session management remain owned by
the `db` package.

## Result Contract

Every public appointment function returns `AppointmentResult`.

```python
AppointmentResult(
    success: bool,
    data: object | None,
    error_code: str | None,
    message: str,
)
