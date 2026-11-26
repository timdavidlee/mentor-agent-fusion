"""One module per concept: truth grain, encoders and rule SQL."""

from generator.concepts.available_to_sell import AvailableToSell
from generator.concepts.base import Concept
from generator.concepts.booked_sale import BookedSale
from generator.concepts.internal_work import InternalWork
from generator.concepts.product_line import ProductLine

CONCEPTS: dict[str, Concept] = {
    c.name: c for c in (ProductLine(), AvailableToSell(), InternalWork(), BookedSale())
}

__all__ = ["CONCEPTS", "Concept"]
