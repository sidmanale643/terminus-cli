from abc import ABC, abstractmethod
import asyncio

class ToolSchema(ABC):
    def __init__():
        pass
    
    def description():
        pass

    @abstractmethod
    def json_schema():
        pass

    @abstractmethod
    def run():
        pass

    async def arun(self, **kwargs):
        """Async execution. Default delegates to sync run in a thread.
        Override for native async behavior."""
        return await asyncio.to_thread(self.run, **kwargs)
