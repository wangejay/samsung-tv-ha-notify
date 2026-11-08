"""Normalize package snapshots and identify arrivals without credential state."""

from dataclasses import dataclass
from datetime import date


class InvalidSnapshot(ValueError):
    """The provider returned a malformed snapshot, not an empty mailbox."""


@dataclass(frozen=True)
class Package:
    """Only the fields needed for a package-arrival notification."""

    package_id: str
    status: int
    package_type: str
    logistics: str


def normalize_packages(data: object) -> tuple[Package, ...]:
    """Preserve provider IDs and statuses; do not infer dates or pickup state."""
    if not isinstance(data, list):
        raise InvalidSnapshot("invalid_package_list")
    result: dict[str, Package] = {}
    for item in data:
        if not isinstance(item, dict):
            raise InvalidSnapshot("invalid_package_record")
        package_id = item.get("pd_id")
        status = item.get("p_status")
        if (
            isinstance(package_id, bool)
            or not isinstance(package_id, (str, int))
            or not str(package_id).strip()
            or isinstance(status, bool)
            or not isinstance(status, (str, int))
        ):
            raise InvalidSnapshot("invalid_package_identity_or_status")
        try:
            normalized_status = int(status)
        except ValueError:
            raise InvalidSnapshot("invalid_package_status") from None
        key = str(package_id).strip()
        package = Package(
            package_id=key,
            status=normalized_status,
            package_type=str(item.get("postal_typeText") or "")[:120],
            logistics=str(item.get("postal_logisticsText") or "")[:120],
        )
        if key in result and result[key].status != normalized_status:
            raise InvalidSnapshot("conflicting_package_status")
        result[key] = package
    return tuple(result.values())


class DailyDeliveryLedger:
    """A stable package ID is due once per Taipei date after successful ACK."""

    def __init__(self, ack_dates: dict[str, str] | None = None) -> None:
        self._ack_dates = dict(ack_dates or {})

    @property
    def ack_dates(self) -> dict[str, str]:
        return dict(self._ack_dates)

    @classmethod
    def from_storage(cls, value: object) -> "DailyDeliveryLedger":
        if not isinstance(value, dict):
            return cls()
        result = {}
        for identifier, day in value.items():
            if not isinstance(identifier, str) or not identifier or not isinstance(day, str):
                continue
            try:
                if date.fromisoformat(day).isoformat() != day:
                    continue
            except ValueError:
                continue
            result[identifier] = day
        return cls(result)

    def due(self, packages: tuple[Package, ...], today: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                package.package_id
                for package in packages
                if package.status == 1 and self._ack_dates.get(package.package_id) != today
            )
        )

    def acknowledge(self, package_ids: set[str], today: str) -> None:
        for identifier in package_ids:
            self._ack_dates[identifier] = today
