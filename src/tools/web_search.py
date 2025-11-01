"""
Web search tool using Tavily API for intelligent web search and content extraction.
"""

import os
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class SearchResult:
    """Represents a single search result from Tavily."""
    title: str
    url: str
    content: str
    snippet: str
    score: float
    raw_content: Optional[str] = None

class TavilyWebSearch:
    """
    Web search tool using Tavily API.
    
    Tavily provides intelligent web search with content extraction and summarization.
    It's particularly good for research, fact-checking, and getting current information.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Tavily web search tool.
        
        Args:
            api_key: Tavily API key. If not provided, will look for TAVILY_API_KEY in environment.
        """
        self.api_key = api_key or os.getenv('TAVILY_API_KEY')
        if not self.api_key:
            raise ValueError("Tavily API key is required. Set TAVILY_API_KEY environment variable or pass api_key parameter.")
        
        self.base_url = "https://api.tavily.com"
        self.search_endpoint = f"{self.base_url}/search"
    
    def search(
        self,
        query: str,
        max_results: int = 5,
        include_answer: bool = True,
        include_raw_content: bool = False,
        search_depth: str = "basic",
        include_images: bool = False,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Perform a web search using Tavily API.
        
        Args:
            query: The search query
            max_results: Maximum number of results to return (1-20)
            include_answer: Include AI-generated answer based on search results
            include_raw_content: Include raw, unprocessed content
            search_depth: "basic" or "advanced" (advanced provides more detailed results)
            include_images: Include image search results
            include_domains: List of domains to specifically include
            exclude_domains: List of domains to exclude
            
        Returns:
            Dictionary containing search results and metadata
        """
        if not query.strip():
            raise ValueError("Search query cannot be empty")
        
        # Prepare the request payload
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max(max_results, 1),
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
            "search_depth": search_depth,
            "include_images": include_images
        }
        
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains
        
        try:
            response = requests.post(
                self.search_endpoint,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Process and structure the results
            results = []
            for result in data.get("results", []):
                search_result = SearchResult(
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    content=result.get("content", ""),
                    snippet=result.get("snippet", ""),
                    score=result.get("score", 0.0),
                    raw_content=result.get("raw_content") if include_raw_content else None
                )
                results.append(search_result)
            
            # Return structured response
            return {
                "query": query,
                "answer": data.get("answer", ""),
                "results": results,
                "images": data.get("images", []) if include_images else [],
                "response_time": data.get("response_time"),
                "credits_used": data.get("credits_used", 0)
            }
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Tavily API request failed: {str(e)}")
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse Tavily API response: {str(e)}")
        except Exception as e:
            raise Exception(f"Unexpected error during Tavily search: {str(e)}")
    
    def quick_search(self, query: str, max_results: int = 3) -> List[SearchResult]:
        """
        Quick search method that returns just the results without metadata.
        
        Args:
            query: The search query
            max_results: Maximum number of results
            
        Returns:
            List of SearchResult objects
        """
        result = self.search(query, max_results=max_results, include_answer=False)
        return result["results"]
    
    def get_answer(self, query: str) -> str:
        """
        Get an AI-generated answer based on web search results.
        
        Args:
            query: The question or query
            
        Returns:
            AI-generated answer based on search results
        """
        result = self.search(query, max_results=5, include_answer=True, include_raw_content=False)
        return result.get("answer", "")

# Convenience function for direct usage
def web_search(
    query: str,
    max_results: int = 5,
    include_answer: bool = True,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function to perform a web search using Tavily.
    
    Args:
        query: The search query
        max_results: Maximum number of results (1-20)
        include_answer: Include AI-generated answer
        api_key: Tavily API key (optional if set in environment)
        
    Returns:
        Search results dictionary
    """
    searcher = TavilyWebSearch(api_key=api_key)
    return searcher.search(query, max_results=max_results, include_answer=include_answer)

# Tool function for integration with the agent framework
def tavily_web_search_tool(query: str, max_results: int = 5) -> str:
    """
    Web search tool using Tavily API.
    
    This tool performs intelligent web searches and can provide AI-generated answers
    based on the search results. It's particularly useful for:
    - Research and fact-checking
    - Getting current information
    - Finding specific information online
    - Getting summaries of topics from multiple sources
    
    Args:
        query: The search query or question
        max_results: Maximum number of results to return (1-10 recommended)
        
    Returns:
        Formatted string containing search results and AI answer (if applicable)
    """
    try:
        searcher = TavilyWebSearch()
        results = searcher.search(query, max_results=max_results, include_answer=True)
        
        # Format the output
        output = []
        output.append(f"Search Query: {results['query']}")
        output.append(f"Results found: {len(results['results'])}")
        
        if results.get('answer'):
            output.append("\nAI Answer:")
            output.append("-" * 40)
            output.append(results['answer'])
        
        output.append("\nSearch Results:")
        output.append("-" * 40)
        
        for i, result in enumerate(results['results'], 1):
            output.append(f"\n{i}. {result.title}")
            output.append(f"   URL: {result.url}")
            output.append(f"   Score: {result.score:.2f}")
            
            # Use snippet if available, otherwise use content
            content_preview = result.snippet if result.snippet else result.content
            if len(content_preview) > 200:
                content_preview = content_preview[:200] + "..."
            output.append(f"   Content: {content_preview}")
        
        if results.get('images'):
            output.append(f"\nImages found: {len(results['images'])}")
        
        output.append(f"\nResponse time: {results.get('response_time', 'N/A')}s")
        output.append(f"Credits used: {results.get('credits_used', 0)}")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"Error performing web search: {str(e)}"

if __name__ == "__main__":
    # Test the tool
    try:
        print("Testing Tavily Web Search Tool...")
        result = tavily_web_search_tool("What are the latest developments in AI in 2024?", max_results=3)
        print(result)
    except Exception as e:
        print(f"Test failed: {str(e)}")
        print("Make sure to set TAVILY_API_KEY in your environment or .env file")