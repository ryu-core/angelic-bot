"""
Serper API Integration
Provides web and image search functionality using Google Serper API
"""

import aiohttp
import config


class SerperAPI:
    """Wrapper for Serper API requests"""
    
    BASE_URL = "https://google.serper.dev"
    
    def __init__(self):
        if not config.SERPER_API_KEY:
            raise ValueError("SERPER_API_KEY not configured in environment variables")
        
        self.headers = {
            'X-API-KEY': config.SERPER_API_KEY,
            'Content-Type': 'application/json'
        }
    
    async def search_web(self, query: str, num_results: int = 5):
        """
        Search the web using Serper API
        
        Args:
            query: Search query string
            num_results: Number of results to return (default: 5)
            
        Returns:
            dict: Search results with 'success', 'results', and optional 'error' keys
        """
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"q": query, "num": num_results, "safe": "active"}
                
                async with session.post(
                    f"{self.BASE_URL}/search",
                    headers=self.headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return {
                            'success': False,
                            'error': f'API returned status {response.status}: {error_text}'
                        }
                    
                    data = await response.json()
                    
                    # Parse organic results
                    results = []
                    if 'organic' in data:
                        for item in data['organic'][:num_results]:
                            results.append({
                                'title': item.get('title', 'No title'),
                                'link': item.get('link', ''),
                                'snippet': item.get('snippet', 'No description available')
                            })
                    
                    return {
                        'success': True,
                        'results': results,
                        'total': len(results)
                    }
                    
        except aiohttp.ClientError as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }
    
    async def search_images(self, query: str, num_results: int = 5):
        """
        Search for images using Serper API
        
        Args:
            query: Search query string
            num_results: Number of results to return (default: 5)
            
        Returns:
            dict: Image search results with 'success', 'images', and optional 'error' keys
        """
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"q": query, "num": num_results, "safe": "active"}
                
                async with session.post(
                    f"{self.BASE_URL}/images",
                    headers=self.headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return {
                            'success': False,
                            'error': f'API returned status {response.status}: {error_text}'
                        }
                    
                    data = await response.json()
                    
                    # Parse image results
                    images = []
                    if 'images' in data:
                        for item in data['images'][:num_results]:
                            images.append({
                                'title': item.get('title', 'No title'),
                                'image_url': item.get('imageUrl', ''),
                                'source_url': item.get('link', ''),
                                'source': item.get('source', 'Unknown source')
                            })
                    
                    return {
                        'success': True,
                        'images': images,
                        'total': len(images)
                    }
                    
        except aiohttp.ClientError as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }


# Convenience functions
async def search_web(query: str, num_results: int = 5):
    """Search the web - convenience wrapper"""
    api = SerperAPI()
    return await api.search_web(query, num_results)


async def search_images(query: str, num_results: int = 5):
    """Search for images - convenience wrapper"""
    api = SerperAPI()
    return await api.search_images(query, num_results)
