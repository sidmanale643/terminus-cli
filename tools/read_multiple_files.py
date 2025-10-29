from textwrap import dedent
from typing import List
import aiofiles
import asyncio
from models.tool import ToolSchema

class MultipleFileReader(ToolSchema):
    def __init__(self):
        self.name = "multiple_file_reader"

    def description(self):
        return dedent("Used for reading multiple files at once")
    
    def json_schema(self):
        return {
        "type": "function",
        "function": {
            "name": self.name, 
            "description": self.description(),
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "the paths of the files to read"
                    }
                },
                "required": ["files"]
            }
        }
    }

    async def read_file(self,file_path):
        async with aiofiles.open(file_path, "r") as f:
            return await f.read()

    async def main(self, files: List[str]):
       
        tasks = [self.read_file(file) for file in files]
        results = await asyncio.gather(*tasks)

        output = []
        for file, content in zip(files, results):
            output.append(f"File Name: {file} \n File Content: {content}")
        
        return "\n\n".join(output)

    def run(self, files):
        return asyncio.run(self.main(files))
