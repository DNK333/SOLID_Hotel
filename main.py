"""Console hotel booking demo built around the five SOLID principles.

SRP: Room types price rooms, the repository stores bookings, the payment
processors handle payments, the notifier sends messages, and BookingService
coordinates the booking workflow.
OCP: New room, payment, or notification types can be added by implementing
their abstractions without changing BookingService.
LSP: Every Room subtype can be used anywhere a Room is expected and honors the
same nightly-price contract.
ISP: PaymentProcessor, Notifier, and BookingRepository are small, focused
interfaces instead of one large general-purpose interface.
DIP: BookingService depends on those abstractions, not concrete payment,
notification, or storage implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from uuid import uuid4


class Room(ABC):
    """Base room contract shared by all room categories."""

    def __init__(self, number: str, base_rate: Decimal) -> None:
        if base_rate <= 0:
            raise ValueError("Стоимость номера должна быть больше нуля.")
        self.number = number
        self.base_rate = base_rate

    @abstractmethod
    def nightly_rate(self) -> Decimal:
        """Return the price for one night."""


class StandardRoom(Room):
    def nightly_rate(self) -> Decimal:
        return self.base_rate


class LuxuryRoom(Room):
    def nightly_rate(self) -> Decimal:
        return self.base_rate * Decimal("1.8")


class FamilyRoom(Room):
    def nightly_rate(self) -> Decimal:
        return self.base_rate * Decimal("1.4")


class Hotel:
    """Owns its rooms (composition) and provides room lookup."""

    def __init__(self, name: str, rooms: list[Room]) -> None:
        self.name = name
        self._rooms = {room.number: room for room in rooms}
        if len(self._rooms) != len(rooms):
            raise ValueError("Номера комнат в отеле должны быть уникальными.")

    def find_room(self, room_number: str) -> Room:
        try:
            return self._rooms[room_number]
        except KeyError as error:
            raise ValueError(f"Номер {room_number} не найден в отеле.") from error


@dataclass(frozen=True)
class Customer:
    name: str
    email: str


class BookingStatus(Enum):
    CONFIRMED = "подтверждено"
    CANCELLED = "отменено"


@dataclass
class Booking:
    booking_id: str
    customer: Customer
    room: Room
    check_in: date
    check_out: date
    total_price: Decimal
    status: BookingStatus = BookingStatus.CONFIRMED

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days


class PaymentProcessor(ABC):
    """Small payment interface, implemented by each supported payment type."""

    @abstractmethod
    def charge(self, amount: Decimal) -> bool:
        pass

    @abstractmethod
    def refund(self, amount: Decimal) -> bool:
        pass


class CardPayment(PaymentProcessor):
    def charge(self, amount: Decimal) -> bool:
        print(f"Оплата картой: {amount:.2f} руб.")
        return True

    def refund(self, amount: Decimal) -> bool:
        print(f"Возврат на карту: {amount:.2f} руб.")
        return True


class CashPayment(PaymentProcessor):
    def charge(self, amount: Decimal) -> bool:
        print(f"Получена оплата наличными: {amount:.2f} руб.")
        return True

    def refund(self, amount: Decimal) -> bool:
        print(f"Возврат наличными: {amount:.2f} руб.")
        return True


class Notifier(ABC):
    @abstractmethod
    def send(self, customer: Customer, message: str) -> None:
        pass


class ConsoleNotifier(Notifier):
    def send(self, customer: Customer, message: str) -> None:
        print(f"Уведомление для {customer.name} ({customer.email}): {message}")


class BookingRepository(ABC):
    @abstractmethod
    def add(self, booking: Booking) -> None:
        pass

    @abstractmethod
    def get(self, booking_id: str) -> Booking:
        pass

    @abstractmethod
    def all(self) -> list[Booking]:
        pass


class InMemoryBookingRepository(BookingRepository):
    def __init__(self) -> None:
        self._bookings: dict[str, Booking] = {}

    def add(self, booking: Booking) -> None:
        self._bookings[booking.booking_id] = booking

    def get(self, booking_id: str) -> Booking:
        try:
            return self._bookings[booking_id]
        except KeyError as error:
            raise ValueError(f"Бронирование {booking_id} не найдено.") from error

    def all(self) -> list[Booking]:
        return list(self._bookings.values())


class BookingService:
    """Coordinates bookings while delegating storage, payment, and messaging."""

    def __init__(
        self,
        hotel: Hotel,
        repository: BookingRepository,
        payment_processor: PaymentProcessor,
        notifier: Notifier,
    ) -> None:
        self._hotel = hotel
        self._repository = repository
        self._payment_processor = payment_processor
        self._notifier = notifier

    def book(
        self, customer: Customer, room_number: str, check_in: date, check_out: date
    ) -> Booking:
        if check_in >= check_out:
            raise ValueError("Дата выезда должна быть позже даты заезда.")

        room = self._hotel.find_room(room_number)
        for existing in self._repository.all():
            overlaps = check_in < existing.check_out and check_out > existing.check_in
            if (
                existing.room.number == room.number
                and existing.status is BookingStatus.CONFIRMED
                and overlaps
            ):
                raise ValueError(f"Номер {room.number} уже занят на эти даты.")

        nights = (check_out - check_in).days
        total_price = room.nightly_rate() * nights
        if not self._payment_processor.charge(total_price):
            raise RuntimeError("Не удалось выполнить оплату; бронирование не создано.")

        booking = Booking(
            booking_id=str(uuid4()),
            customer=customer,
            room=room,
            check_in=check_in,
            check_out=check_out,
            total_price=total_price,
        )
        self._repository.add(booking)
        self._notifier.send(
            customer,
            f"Бронирование {booking.booking_id} подтверждено: "
            f"номер {room.number}, {nights} ноч., сумма {total_price:.2f} руб.",
        )
        return booking

    def cancel(self, booking_id: str) -> None:
        booking = self._repository.get(booking_id)
        if booking.status is BookingStatus.CANCELLED:
            raise ValueError("Бронирование уже отменено.")
        if not self._payment_processor.refund(booking.total_price):
            raise RuntimeError("Не удалось выполнить возврат; бронь не отменена.")

        booking.status = BookingStatus.CANCELLED
        self._notifier.send(
            booking.customer,
            f"Бронирование {booking.booking_id} отменено. "
            f"Возвращено {booking.total_price:.2f} руб.",
        )


def main() -> None:
    hotel = Hotel(
        "Отель SOLID",
        [
            StandardRoom("101", Decimal("5000")),
            LuxuryRoom("201", Decimal("10000")),
            FamilyRoom("301", Decimal("7000")),
        ],
    )
    repository = InMemoryBookingRepository()
    service = BookingService(
        hotel=hotel,
        repository=repository,
        payment_processor=CardPayment(),
        notifier=ConsoleNotifier(),
    )
    customer = Customer("Анна Иванова", "anna@example.com")

    print(f"Добро пожаловать в {hotel.name}!")
    booking = service.book(
        customer,
        room_number="201",
        check_in=date(2027, 6, 10),
        check_out=date(2027, 6, 13),
    )
    print(
        f"Итого: {booking.nights} ночи, "
        f"{booking.total_price:.2f} руб., статус: {booking.status.value}."
    )

    cash_service = BookingService(
        hotel=hotel,
        repository=repository,
        payment_processor=CashPayment(),
        notifier=ConsoleNotifier(),
    )
    cash_service.book(
        customer,
        room_number="101",
        check_in=date(2027, 6, 10),
        check_out=date(2027, 6, 12),
    )

    service.cancel(booking.booking_id)
    print(f"Итоговый статус бронирования: {booking.status.value}.")


if __name__ == "__main__":
    main()
