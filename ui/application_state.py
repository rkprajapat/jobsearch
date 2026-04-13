# Application state manager for tracking and updating opportunities
from datetime import datetime, timezone
from typing import Callable
from models.opportunity import Opportunity, save_opportunities
from nicegui import run


class ApplicationStateManager:
    """Manages application tracking state and persistence."""
    
    def __init__(self, opportunities: list[Opportunity]):
        self.opportunities = opportunities
        self._update_callbacks: list[Callable[[], None]] = []
    
    def on_state_changed(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when state changes."""
        self._update_callbacks.append(callback)
    
    async def _notify_update(self) -> None:
        """Notify all registered callbacks of state change."""
        for callback in self._update_callbacks:
            callback()
    
    async def update_relevant_status(self, opp: Opportunity, relevant: bool) -> bool:
        """Update relevant status and persist."""
        opp.relevant = relevant
        return await self._persist(opp)
    
    async def update_applied_status(self, opp: Opportunity, applied: bool) -> bool:
        """Update applied status and persist. Sets applied_date if marking as applied."""
        was_applied = opp.applied
        opp.applied = applied
        opp.applied_date = datetime.now(timezone.utc) if applied else None
        
        success = await self._persist(opp)
        if success and was_applied != applied:
            await self._notify_update()
        return success
    
    async def _persist(self, opp: Opportunity) -> bool:
        """Persist a single opportunity update to storage."""
        try:
            success = await run.io_bound(save_opportunities, opp)
            return success
        except Exception as e:
            print(f"Error persisting opportunity update: {e}")
            return False
    
    def get_applied_count(self) -> int:
        """Get count of applied opportunities."""
        return sum(1 for opp in self.opportunities if opp.applied)
    
    def get_not_applied_count(self) -> int:
        """Get count of opportunities not yet applied to."""
        return len(self.opportunities) - self.get_applied_count()
    
    def get_sorted_opportunities(self) -> list[Opportunity]:
        """Get opportunities sorted by relevance, application status, and date."""
        sorted_opps = sorted(
            self.opportunities,
            key=lambda opp: (opp.relevant, not opp.applied, opp.date_posted),
            reverse=True
        )
        return sorted_opps
    
    @staticmethod
    def filter_complete_opportunities(opps: list[Opportunity]) -> list[Opportunity]:
        """Filter opportunities with required fields."""
        required_fields = ["designation", "company_name"]
        return [
            opp for opp in opps
            if all(getattr(opp, field) for field in required_fields)
        ]
