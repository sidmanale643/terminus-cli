from abc import ABC, abstractmethod


class ToolSchema(ABC):
    def __init__(self):
        pass

    def description(self):
        pass

    @abstractmethod
    def json_schema(self):
        pass

    @abstractmethod
    def run(self, **kwargs):
        pass
