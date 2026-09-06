from __future__ import annotations

from django.test import SimpleTestCase

from ingest.fake_names import (
    ADJECTIVES,
    DESCRIPTORS,
    NOUNS,
    SUFFIX_ALPHABET,
    SUFFIX_LENGTH,
    generate_fake_name,
)


class GenerateFakeNameTests(SimpleTestCase):
    def test_returns_three_capitalized_words_and_a_suffix(self):
        name = generate_fake_name()

        adjective, descriptor, noun_and_suffix = name.split(" ")
        noun, _, suffix = noun_and_suffix.partition("-")
        for word in (adjective, descriptor, noun):
            self.assertEqual(word, word.capitalize())
        self.assertEqual(len(suffix), SUFFIX_LENGTH)
        for character in suffix:
            self.assertIn(character, SUFFIX_ALPHABET)

    def test_words_come_from_the_word_lists(self):
        name = generate_fake_name()

        adjective, descriptor, noun_and_suffix = name.split(" ")
        noun, _, _suffix = noun_and_suffix.partition("-")
        self.assertIn(adjective.lower(), ADJECTIVES)
        self.assertIn(descriptor.lower(), DESCRIPTORS)
        self.assertIn(noun.lower(), NOUNS)

    def test_word_lists_have_no_internal_duplicates(self):
        for word_list in (ADJECTIVES, DESCRIPTORS, NOUNS):
            self.assertEqual(len(word_list), len(set(word_list)))

    def test_word_lists_are_sorted(self):
        for word_list in (ADJECTIVES, DESCRIPTORS, NOUNS):
            self.assertEqual(word_list, sorted(word_list))

    def test_combination_space_is_at_least_ten_million(self):
        total = (
            len(ADJECTIVES)
            * len(DESCRIPTORS)
            * len(NOUNS)
            * len(SUFFIX_ALPHABET) ** SUFFIX_LENGTH
        )
        self.assertGreaterEqual(total, 10_000_000)

    def test_varies_across_calls(self):
        names = {generate_fake_name() for _ in range(50)}

        self.assertGreater(len(names), 1)
