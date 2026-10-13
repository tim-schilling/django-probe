from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.test import Client, TestCase
from django.urls import get_resolver, reverse
from django.utils import timezone

from ingest.models import Submission
from ingest.stats import MINIMUM_PROJECTS, StatsFilterForm
from ingest.tests.factories import ProjectFactory, SubmissionFactory, UserFactory


def submit_projects(count: int, **fields) -> None:
    for _ in range(count):
        SubmissionFactory(project=ProjectFactory(), **fields)


class StatsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        submit_projects(
            MINIMUM_PROJECTS,
            django_version="5.1.2",
            python_version="3.12.3",
            files_scanned=12,
            # Only Django's own settings are public; others may be private.
            django_settings={"CACHES": 1, "ACME_FLAG": 1},
            # Only recognized Django names are public; other packages stay private.
            usage={
                "django.db.models.F": 4,
                "django.my_random.offensive_statement": 1,
                "acme.billing.charge": 1,
            },
        )
        submit_projects(
            MINIMUM_PROJECTS,
            django_version="4.2.16",
            python_version="3.12.1",
            files_scanned=300,
            django_settings={"CACHES": 1, "TEMPLATES": 1},
        )
        submit_projects(
            1,
            django_version="3.2.0",
            python_version="3.9.1",
            files_scanned=12,
            # Stored keys are untrusted; malformed ones are never published.
            django_settings={"CACHE_MIDDLEWARE_SECONDS": 1, "'; DROP TABLE x; --": 1},
            usage={"django.<script>": 1, "django.%s": 1},
        )
        # Anonymous submissions can't be deduplicated, so they're never counted.
        SubmissionFactory.create_batch(MINIMUM_PROJECTS, django_version="6.0")

    def get_stats(self, query: str = "", url: str = "api-stats") -> dict:
        response = self.client.get(f"{reverse(url)}{query}")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_unknown_project_version_does_not_use_scanner(self):
        SubmissionFactory(
            project=ProjectFactory(),
            schema_version=2,
            python_version="3.15.0",
        )

        stats = self.get_stats()

        self.assertEqual(stats["distributions"]["python"]["other"], 2)
        self.assertEqual(
            Submission.objects.with_minor_versions()
            .filter(python_minor="3.15")
            .count(),
            0,
        )

    def test_counts_latest_submission_per_project(self):
        """Only a project's latest submission counts, and newer versions are listed."""
        project = Submission.objects.filter(django_version="3.2.0").get().project
        Submission.objects.filter(project=project).update(
            created_at=timezone.now() - timedelta(days=30)
        )
        SubmissionFactory(project=project, django_version="6.2a1")

        stats = self.get_stats()

        self.assertEqual(stats["projects"], 2 * MINIMUM_PROJECTS + 1)
        self.assertEqual(
            stats["distributions"]["django"],
            {
                "values": [
                    {"value": "6.2", "label": "6.2", "projects": 1},
                    {"value": "6.1", "label": "6.1", "projects": 0},
                    {"value": "6.0", "label": "6.0", "projects": 0},
                    {"value": "5.2", "label": "5.2", "projects": 0},
                    {"value": "5.1", "label": "5.1", "projects": MINIMUM_PROJECTS},
                    {"value": "5.0", "label": "5.0", "projects": 0},
                    {"value": "4.2", "label": "4.2", "projects": MINIMUM_PROJECTS},
                ],
                "other": 0,
            },
        )

    def test_distributions(self):
        """Modern versions are listed even with no projects, and counts are exact."""
        stats = self.get_stats()

        self.assertFalse(stats["withheld"])
        self.assertEqual(stats["projects"], 2 * MINIMUM_PROJECTS + 1)
        self.assertEqual(
            [row["value"] for row in stats["distributions"]["django"]["values"]],
            ["6.1", "6.0", "5.2", "5.1", "5.0", "4.2"],
        )
        self.assertEqual(stats["distributions"]["django"]["other"], 1)
        self.assertEqual(
            stats["distributions"]["python"],
            {
                "values": [
                    {"value": "3.14", "label": "3.14", "projects": 0},
                    {"value": "3.13", "label": "3.13", "projects": 0},
                    {
                        "value": "3.12",
                        "label": "3.12",
                        "projects": 2 * MINIMUM_PROJECTS,
                    },
                    {"value": "3.11", "label": "3.11", "projects": 0},
                ],
                "other": 1,
            },
        )
        self.assertEqual(
            [
                (row["value"], row["projects"])
                for row in stats["distributions"]["size"]["values"]
            ],
            [
                ("small", MINIMUM_PROJECTS + 1),
                ("medium", 0),
                ("large", MINIMUM_PROJECTS),
                ("very-large", 0),
            ],
        )
        self.assertEqual(
            stats["popular"],
            {
                "setting": [
                    {
                        "key": "CACHES",
                        "source": "setting",
                        "projects": 2 * MINIMUM_PROJECTS,
                    },
                    {
                        "key": "TEMPLATES",
                        "source": "setting",
                        "projects": MINIMUM_PROJECTS,
                    },
                ],
                "usage": [
                    {
                        "key": "django.db.models.F",
                        "source": "usage",
                        "projects": MINIMUM_PROJECTS,
                    },
                ],
            },
        )
        self.assertNotIn("keys", stats)

        matrix = stats["django_python"]
        self.assertEqual(matrix["python"], ["3.14", "3.13", "3.12", "3.11", None])
        self.assertEqual(
            {
                row["django"]: [cell["projects"] for cell in row["cells"]]
                for row in matrix["rows"]
            },
            {
                "6.1": [0, 0, 0, 0, 0],
                "6.0": [0, 0, 0, 0, 0],
                "5.2": [0, 0, 0, 0, 0],
                "5.1": [0, 0, MINIMUM_PROJECTS, 0, 0],
                "5.0": [0, 0, 0, 0, 0],
                "4.2": [0, 0, MINIMUM_PROJECTS, 0, 0],
                None: [0, 0, 0, 0, 1],
            },
        )

    def test_filters(self):
        self.assertEqual(self.get_stats("?django=5.1")["projects"], MINIMUM_PROJECTS)
        self.assertEqual(
            self.get_stats("?python=3.12&size=large")["projects"], MINIMUM_PROJECTS
        )
        self.assertEqual(
            self.get_stats("?key=CACHES")["projects"], 2 * MINIMUM_PROJECTS
        )
        self.assertEqual(
            self.get_stats("?key=django.db.models.F")["projects"], MINIMUM_PROJECTS
        )

    def test_chained_keys(self):
        """Every key must be used, so each one narrows the projects further."""
        self.assertEqual(
            self.get_stats("?key=CACHES&key=TEMPLATES")["projects"], MINIMUM_PROJECTS
        )
        self.assertEqual(
            self.get_stats("?key=CACHES&key=django.db.models.F")["projects"],
            MINIMUM_PROJECTS,
        )
        self.assertTrue(
            self.get_stats("?key=TEMPLATES&key=django.db.models.F")["withheld"]
        )

    def test_withheld(self):
        """Fewer than the minimum projects returns no figures at all."""
        self.assertEqual(
            self.get_stats("?django=3.2"),
            {
                "minimum_projects": MINIMUM_PROJECTS,
                "filters": {"django": "3.2"},
                "withheld": True,
                "projects": None,
                "distributions": {},
                "django_python": {},
                "popular": {},
            },
        )
        self.assertEqual(
            self.get_stats("?django=3.2", url="api-stats-keys"),
            {
                "minimum_projects": MINIMUM_PROJECTS,
                "filters": {"django": "3.2"},
                "withheld": True,
                "projects": None,
                "keys": [],
            },
        )
        self.assertTrue(self.get_stats("?django=6.0")["withheld"])

    def test_keys(self):
        """Every name, counted only at the minimum.

        Settings come first, then counted names ahead of the rest, then alphabetical.
        """
        keys = self.get_stats(url="api-stats-keys")["keys"]
        counts = {row["key"]: row["projects"] for row in keys}

        self.assertEqual(counts["CACHES"], 2 * MINIMUM_PROJECTS)
        self.assertEqual(counts["TEMPLATES"], MINIMUM_PROJECTS)
        self.assertIsNone(counts["CACHE_MIDDLEWARE_SECONDS"])
        self.assertIsNone(counts["USE_TZ"])
        self.assertEqual(counts["django.db.models.F"], MINIMUM_PROJECTS)
        self.assertNotIn("acme.billing.charge", counts)
        self.assertNotIn("django.my_random.offensive_statement", counts)
        self.assertNotIn("ACME_FLAG", counts)
        self.assertEqual(
            [key for key in counts if not StatsFilterForm({"key": [key]}).is_valid()],
            [],
        )
        self.assertEqual(
            [row["source"] for row in keys],
            sorted(row["source"] for row in keys),
        )
        settings = [row for row in keys if row["source"] == "setting"]
        self.assertEqual(
            [row["key"] for row in settings[:3]],
            ["CACHES", "TEMPLATES", "ABSOLUTE_URL_OVERRIDES"],
        )
        self.assertEqual(
            settings,
            sorted(
                settings,
                key=lambda row: (row["projects"] is None, row["key"].lower()),
            ),
        )
        filtered = self.get_stats("?django=4.2", url="api-stats-keys")["keys"]
        self.assertIn(
            {"key": "CACHE_MIDDLEWARE_SECONDS", "source": "setting", "projects": None},
            filtered,
        )
        self.assertNotIn("django.db.models.F", {row["key"] for row in filtered})
        self.assertTrue(self.get_stats("?django=3.2", url="api-stats-keys")["withheld"])

    def test_invalid_queries(self):
        for query in [
            "?page=2",
            "?django=5.1&django=4.2",
            "?django=5",
            "?django=05.1",
            "?size=huge",
            "?key=a%20b",
            "?key=caches",
            "?key=ACME_FLAG",
            "?key=acme.billing.charge",
            "?q=cache",
            "?" + "&".join(f"key=django.k{number}" for number in range(11)),
        ]:
            with self.subTest(query=query):
                self.assertEqual(
                    self.client.get(f"{reverse('api-stats')}{query}").status_code, 404
                )
                self.assertEqual(
                    self.client.get(f"{reverse('stats')}{query}").status_code, 404
                )

    def test_canonical_redirect(self):
        """The canonical order is alphabetical because Cloudflare sorts query strings.

        Any other order would redirect to itself forever behind it.
        """
        for url, expected in [
            ("stats", "/stats/?django=5.1&key=CACHES&size=small"),
            ("api-stats", "/api/stats/?django=5.1&key=CACHES&size=small"),
        ]:
            with self.subTest(url=url):
                response = self.client.get(
                    f"{reverse(url)}?size=small&python=&key=CACHES&django=5.1"
                )
                self.assertRedirects(response, expected, fetch_redirect_response=False)
        self.assertRedirects(
            self.client.get(f"{reverse('stats')}?python="),
            "/stats/",
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get(f"{reverse('stats')}?key=TEMPLATES&key=CACHES&key=CACHES"),
            "/stats/?key=CACHES&key=TEMPLATES",
            fetch_redirect_response=False,
        )

    def test_page(self):
        response = self.client.get(reverse("stats"))

        self.assertContains(
            response,
            '<p class="stats-count" id="project-count">'
            '<span class="stat">21</span> projects</p>',
            html=True,
        )
        self.assertContains(response, 'href="/stats/?key=CACHES"')
        self.assertContains(response, 'href="/stats/?django=5.1"')
        self.assertNotContains(response, 'href="/stats/?django=6.1"')
        self.assertContains(response, 'href="/stats/settings/"')
        self.assertContains(
            response,
            '<tr><td class="table__meta">Older or unrecognized</td>'
            '<td>1</td><td class="table__meta">5%</td></tr>',
            html=True,
        )
        self.assertNotContains(response, "CACHE_MIDDLEWARE_SECONDS")
        self.assertContains(response, "<td>0</td>", html=True)
        self.assertContains(response, 'href="/api/stats/"')
        self.assertContains(response, 'data-stats-search="/api/stats/keys/"')
        self.assertContains(
            response, '<form action="/stats/" class="stats-search" hidden>'
        )
        self.assertContains(response, 'id="django-python"')
        self.assertContains(
            response, '<a href="/stats/?django=5.1&amp;python=3.12">10</a>'
        )
        self.assertContains(
            self.client.get(f"{reverse('stats')}?django=3.2"),
            "so the results are withheld",
        )

        response = self.client.get(f"{reverse('stats')}?key=CACHES&key=TEMPLATES")

        self.assertContains(response, 'href="/stats/?key=TEMPLATES">(remove)</a>')
        self.assertContains(response, 'href="/stats/?key=CACHES">(remove)</a>')
        self.assertContains(
            response,
            'data-stats-search="/api/stats/keys/?key=CACHES&amp;key=TEMPLATES"',
        )
        self.assertContains(
            response, '<input type="hidden" name="key" value="TEMPLATES">'
        )
        self.assertNotContains(response, 'href="/stats/?key=CACHES&amp;key=TEMPLATES"')

        response = self.client.get(f"{reverse('stats')}?key=CACHES")

        self.assertContains(response, 'href="/stats/?key=CACHES&amp;key=TEMPLATES"')

    def test_browse(self):
        """Names link to the same page, narrowed to the projects using them.

        Names below the minimum are listed without a count or a link, and the
        breadcrumb leads back to the overview with the filters kept.
        """
        response = self.client.get(f"{reverse('stats-apis')}?django=5.1")

        self.assertContains(response, "All Django APIs")
        self.assertContains(response, '<span class="stat">10</span>', html=True)
        self.assertContains(
            response, 'href="/stats/apis/?django=5.1&amp;key=django.db.models.F"'
        )
        self.assertContains(
            response, '<li><a href="/stats/?django=5.1">Stats</a></li>', html=True
        )
        self.assertContains(
            response, '<form action="/stats/apis/" class="stats-search" hidden>'
        )
        self.assertNotContains(response, "TEMPLATES")

        response = self.client.get(reverse("stats-settings"))

        self.assertContains(response, 'href="/stats/settings/?key=TEMPLATES"')
        for name in ["CACHE_MIDDLEWARE_SECONDS", "USE_TZ"]:
            self.assertContains(
                response,
                f"<tr><td><code>{name}</code></td>"
                '<td colspan="2" class="table__meta">Too few projects</td></tr>',
                html=True,
            )

    def test_publicly_cacheable(self):
        """Shared caches must be able to serve one copy to every visitor.

        Covers every URL whose view uses ``stats_cache_control``. Whoever's request
        fills the cache, a first-time visitor or a signed-in user, the response
        sets no session or CSRF cookie.
        """
        urls = [
            pattern.name
            for pattern in get_resolver().url_patterns
            if getattr(pattern.callback, "publicly_cached", False)
        ]
        self.assertIn("stats", urls)
        signed_in = Client()
        signed_in.force_login(UserFactory())
        for visitor, client in [("first-time", Client()), ("signed-in", signed_in)]:
            for url in urls:
                with self.subTest(visitor=visitor, url=url):
                    response = client.get(reverse(url))

                    self.assertEqual(
                        response["Cache-Control"],
                        "public, max-age=300, s-maxage=86400",
                    )
                    self.assertNotIn("Cookie", response.get("Vary", ""))
                    self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)
                    self.assertNotIn(settings.CSRF_COOKIE_NAME, response.cookies)
                    self.assertEqual(response.cookies, {})
                    self.assertNotContains(response, "Sign out")
                    self.assertNotContains(response, "csrfmiddlewaretoken")
