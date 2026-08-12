import asyncio

from backend.app.db import RFEvent, SessionLocal
from backend.app.events import EventService
from backend.app.models import RFFrame


def test_process_persists_frame_with_enrichment_fields() -> None:
    service = EventService(300)
    frame = RFFrame(
        code="F6A948",
        sync=12324,
        low=440,
        high=1212,
        source_bridge="tasmota_A3F90F",
        device_id=None,
        device_name=None,
        action=None,
    )
    processed = asyncio.run(service.process(frame))
    assert processed.code == "F6A948"
    with SessionLocal() as db:
        saved = db.query(RFEvent).filter(RFEvent.code == "F6A948").order_by(RFEvent.id.desc()).first()
        assert saved is not None
        assert saved.source_bridge == "tasmota_A3F90F"
        db.delete(saved)
        db.commit()
