from .base import Item, Source
from .github import GitHubTrending, GitHubRising
from .arxiv import ArxivSource
from .hackernews import HackerNewsSource
from .huggingface import HuggingFacePapers
from .huggingface_blog import HuggingFaceBlog
from .qbitai import QbitaiSource
from .anthropic import AnthropicSource
from .openai import OpenAISource
from .google_research import GoogleResearchSource
from .deepmind import DeepMindSource
from .meta_ai import MetaAISource

REGISTRY = {
    "github_trending": GitHubTrending,
    "github_rising": GitHubRising,
    "arxiv": ArxivSource,
    "hackernews": HackerNewsSource,
    "huggingface_papers": HuggingFacePapers,
    "huggingface_blog": HuggingFaceBlog,
    "qbitai": QbitaiSource,
    "anthropic": AnthropicSource,
    "openai": OpenAISource,
    "google_research": GoogleResearchSource,
    "deepmind": DeepMindSource,
    "meta_ai": MetaAISource,
}
