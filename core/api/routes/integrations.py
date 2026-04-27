from fastapi import APIRouter
from pydantic import BaseModel

from core.integrations.router import IntegrationRouter
from core.integrations.state import VesselStateAggregator
from core.integrations.store import IntegrationEventStore

router = APIRouter()
integration_router = IntegrationRouter()
integration_store = IntegrationEventStore()
state_aggregator = VesselStateAggregator()


class ParseRequest(BaseModel):
    payload: str


@router.post("/api/v1/integrations/parse")
async def parse_integration_payload(request: ParseRequest):
    events = integration_router.route(request.payload)
    integration_store.append_many(events)
    return {"count": len(events), "events": [event.model_dump(mode="json") for event in events]}


@router.get("/api/v1/integrations/events")
async def list_integration_events(limit: int = 50):
    events = integration_store.recent(limit=max(1, min(limit, 500)))
    return {"count": len(events), "events": events}


@router.get("/api/v1/integrations/vessels")
async def list_vessel_state():
    return state_aggregator.build(integration_store.all())


@router.get("/api/v1/integrations/vessels/geojson")
async def vessel_state_geojson():
    state = state_aggregator.build(integration_store.all())
    return state["geojson"]


@router.get("/api/v1/chokepoints")
async def chokepoint_status():
    from core.chokepoints.monitor import count_vessels_at_chokepoints
    state = state_aggregator.build(integration_store.all())
    features = state["geojson"]["features"]
    counts = count_vessels_at_chokepoints(features)
    return {"chokepoints": counts, "total_vessels": state["summary"]["positioned_vessels"]}
