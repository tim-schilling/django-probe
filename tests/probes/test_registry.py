from __future__ import annotations

from unittest import TestCase

from django_probe import ast_probe
from django_probe.ast_probe import probe_names
from django_probe.probes import Probe


class RegistryTests(TestCase):
    def test_names_have_no_separator(self):
        """The ':' separator is reserved for joining a namespace to a probe name."""
        for key in probe_names():
            namespace, _, name = key.partition(":")
            self.assertNotIn(":", namespace)
            self.assertNotIn(":", name)

    def test_rejects_separator_in_name_or_namespace(self):
        with self.assertRaises(RuntimeError):
            Probe("bad:name")
        with self.assertRaises(RuntimeError):
            Probe("name", namespace="bad:namespace")
        with self.assertRaises(RuntimeError):
            Probe("bad.name")

    def test_same_name_different_namespaces_do_not_collide(self):
        """Two namespaces may each register a probe under the same bare name."""

        first = Probe("shared_probe_name", namespace="alpha")
        self.addCleanup(ast_probe._REGISTRY.pop, "alpha:shared_probe_name")

        second = Probe("shared_probe_name", namespace="beta")
        self.addCleanup(ast_probe._REGISTRY.pop, "beta:shared_probe_name")

        self.assertIsNot(first._registration, second._registration)
        self.assertIn("alpha:shared_probe_name", probe_names())
        self.assertIn("beta:shared_probe_name", probe_names())

    def test_duplicate_registration_raises(self):
        Probe("dup_probe_name", namespace="dupe-ns")
        self.addCleanup(ast_probe._REGISTRY.pop, "dupe-ns:dup_probe_name")

        with self.assertRaises(RuntimeError):
            Probe("dup_probe_name", namespace="dupe-ns")
