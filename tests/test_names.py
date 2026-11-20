import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.editorial_store import EditorialStore
from app.genealogy import Event, GedcomRepository, Person


class NameTests(unittest.TestCase):
    def test_automatic_forms_preserve_raw_names(self):
        cases = [
            ('Arne Olav /Halvorsen/', 'Arne Halvorsen', 'Arne Olav Halvorsen', 'formal', 'Arne Olav Halvorsen'),
            ('Margaret "Peggy" Ann /Brennan/', 'Peggy Brennan', 'Margaret Ann Brennan', 'informal', 'Peggy'),
            ('Ingrid /Moe (Fraser)/', 'Ingrid Moe', 'Ingrid Moe', 'married', 'Fraser'),
            ('Kari /(Halvorson) Halvorsen/', 'Kari Halvorsen', 'Kari Halvorsen', 'variant', 'Halvorson'),
        ]
        for raw, display, formal, kind, text in cases:
            with self.subTest(raw=raw):
                person = Person('P', name=raw)
                self.assertEqual(person.display_name, display)
                self.assertEqual(person.formal_name, formal)
                self.assertIn({'type': kind, 'text': text}, person.name_forms)
                self.assertEqual(person.name, raw)

    def test_import_search_privacy_and_removal_on_next_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gedcom = root / 'names.ged'
            gedcom.write_text('''0 @P1@ INDI
1 NAME Arne Olav /Halvorsen/
1 BIRT
2 DATE 1930
1 DEAT
2 DATE 2011
0 @P2@ INDI
1 NAME Kari /(Halvorson) Halvorsen/
1 DEAT
2 DATE 1900
0 @P3@ INDI
1 NAME Ingeborg Marie "Inga" /Lid/
1 BIRT
2 DATE 1850
2 PLAC Göteborg
1 DEAT
2 DATE 1930
0 @P4@ INDI
1 NAME Private /Relative/
0 TRLR
''', encoding='utf-8')
            db = root / 'editorial.sqlite3'
            store = EditorialStore(db)
            repo = GedcomRepository(gedcom)
            csv = root / 'names.csv'
            header = 'gedcom_id,name_type,name,note\n'
            app = create_app({'TESTING': True, 'GEDCOM_PATH': str(gedcom), 'EDITORIAL_DB_PATH': str(db)})
            client = app.test_client()
            self.assertEqual(client.get('/api/search?q=bud+halvorsen&surnames=0').json, [])
            csv.write_text(header + 'P1,informal,Bud,\n', encoding='utf-8')
            store.import_names(csv, repo)
            self.assertEqual(client.get('/api/search?q=bud+halvorsen&surnames=0').json[0]['name'], 'Bud Halvorsen')
            self.assertIn(b'Arne Olav Halvorsen', client.get('/people/P1').data)
            self.assertEqual(store.name_forms_for_identifier('gedcom_xref', 'P1')[1]['text'], 'Bud')
            hits = client.get('/api/search?q=halvorson').json
            self.assertEqual({row['kind'] for row in hits}, {'surname', 'person'})
            for query in ['grandma+inga', 'goteborg']:
                self.assertEqual(client.get('/api/search?q=' + query + '&surnames=0').json[0]['id'], 'P3')
            self.assertEqual(client.get('/api/search?q=inga+nonexistent&surnames=0').json, [])
            for identifier in ['P4', 'UNKNOWN']:
                csv.write_text(header + f'{identifier},informal,Alias,\n', encoding='utf-8')
                with self.assertRaises(ValueError):
                    store.import_names(csv, repo)
            self.assertEqual(store.name_forms_for_identifier('gedcom_xref', 'P4'), [])
            csv.write_text(header, encoding='utf-8')
            store.import_names(csv, repo)
            self.assertEqual(client.get('/api/search?q=bud+halvorsen&surnames=0').json, [])
            self.assertEqual(client.get('/api/search?q=arne+halvorsen&surnames=0').json[0]['name'], 'Arne Halvorsen')
