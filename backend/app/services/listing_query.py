"""Shared queries — only user-filter matches are stored and shown."""
from sqlalchemy.orm import Session

from app.models import Listing, ListingStatus

MATCHED_LISTING_STATUSES = (ListingStatus.MATCHED, ListingStatus.NOTIFIED)


def matched_listings_query(db: Session):
    return db.query(Listing).filter(Listing.status.in_(MATCHED_LISTING_STATUSES))
