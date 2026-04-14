"""Persistent storage for Decibench runs and production call traces."""

from decibench.store.sqlite import RunStore, default_store_path

__all__ = ["RunStore", "default_store_path"]
