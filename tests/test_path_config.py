"""Unit tests for PathConfig.path_cards() deduplication behavior."""
import os
import tempfile
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from path_config import PathConfig


def test_path_cards_deduplicates_by_absolute_form():
    """Test that path_cards() deduplicates paths via absolute form normalization.
    
    Verifies that multiple references to the same absolute path produce only
    a single card, even when provided in different relative or symbolic forms.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test vault directory
        vault_path = os.path.join(tmpdir, "vault")
        os.makedirs(vault_path)
        
        # Create a test repo directory
        repo_path = os.path.join(tmpdir, "repo")
        os.makedirs(repo_path)
        
        # Construct env dict with duplicate paths in different forms:
        # - vault_path specified both via OBSIDIAN_VAULT_PATH and in recent_paths
        # - repo_path appearing multiple times in VAULT_OS_REPOS
        env = {
            "OBSIDIAN_VAULT_PATH": vault_path,
            "VAULT_OS_REPOS": f"{repo_path},{repo_path}",  # Explicit duplicate
        }
        
        # Create a mock PathConfig with controlled env and mocked _data
        config = PathConfig(env, tmpdir)
        
        # Inject duplicate paths into recent_paths to trigger deduplication
        config._data["recent_paths"] = [
            vault_path,  # Same as OBSIDIAN_VAULT_PATH
            os.path.join(vault_path),  # Same path, no-op normalization
        ]
        
        # Get cards
        cards = config.path_cards()
        
        # Collect all absolute paths from cards
        card_paths = [card["path"] for card in cards]
        
        # Assert: each absolute path appears exactly once
        assert len(card_paths) == len(set(card_paths)), \
            f"Duplicate paths found in cards: {card_paths}"
        
        # Assert: vault_path appears exactly once (from env, not from recent_paths)
        vault_cards = [c for c in cards if c["path"] == os.path.abspath(vault_path)]
        assert len(vault_cards) == 1, \
            f"Expected 1 vault card, got {len(vault_cards)}"
        
        # Assert: repo_path appears exactly once (deduped from VAULT_OS_REPOS duplicates)
        repo_cards = [c for c in cards if c["path"] == os.path.abspath(repo_path)]
        assert len(repo_cards) == 1, \
            f"Expected 1 repo card, got {len(repo_cards)}"
        
        # Assert: vault and repo cards are marked with correct metadata
        vault_card = vault_cards[0]
        assert vault_card["label"] == "Obsidian Vault"
        assert vault_card["group"] == "vault"
        assert vault_card["type"] == "vault"
        assert vault_card["exists"] is True
        
        repo_card = repo_cards[0]
        assert repo_card["group"] == "known repos"
        assert repo_card["type"] == "repo"
        assert repo_card["exists"] is True


def test_path_cards_skips_empty_env_values():
    """Test that empty or whitespace-only env values are skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = os.path.join(tmpdir, "vault")
        os.makedirs(vault_path)
        
        # Env with empty strings and whitespace
        env = {
            "OBSIDIAN_VAULT_PATH": "",
            "VAULT_OS_REPOS": ",  , , ",  # Only whitespace and commas
        }
        
        config = PathConfig(env, tmpdir)
        config._data["recent_paths"] = []
        
        cards = config.path_cards()
        
        # Should still include app_dir and home shortcuts, but no vault/repo cards
        # from the empty env values
        assert len(cards) > 0  # app_dir is always added
        assert not any(c["group"] == "vault" for c in cards), \
            "Should not create vault cards from empty env"


def test_path_cards_absolute_form_normalization():
    """Test that relative paths are normalized to absolute form for deduplication.
    
    The seen-set uses absolute form; paths with ./ prefix or relative refs
    should still deduplicate correctly.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = os.path.join(tmpdir, "repo")
        os.makedirs(repo_path)
        
        # Save current working directory and change to tmpdir for relative path test
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            
            # Relative form of repo
            relative_repo = "./repo"
            
            env = {
                "VAULT_OS_REPOS": f"{relative_repo},{repo_path}",
            }
            
            config = PathConfig(env, tmpdir)
            
            cards = config.path_cards()
            
            # Should have exactly one repo card despite different forms
            repo_cards = [c for c in cards if c["group"] == "known repos" and c["type"] == "repo"]
            # Filter to just the one we added (may have others from grok scan)
            matching_repo_cards = [c for c in repo_cards if "repo" in c["path"]]
            
            repo_count = sum(1 for c in matching_repo_cards if os.path.samefile(c["path"], repo_path))
            assert repo_count == 1, \
                f"Expected 1 repo card with same path, got {repo_count}"
        
        finally:
            os.chdir(original_cwd)
