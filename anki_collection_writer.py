import json
import sqlite3
from collections import OrderedDict
from copy import deepcopy

from anki_base import *
from misc import *
from util import *
import re

# logger = get_logger("AnkiCollectionWriter")


class AnkiCollectionWriter:
    def __init__(self,
                 root_deck_name: str,
                 collection_path: str,
                 cats_df: OrderedDict,
                 cards_df: OrderedDict,
                 tpls_df: OrderedDict
                 ):
        assert os.path.exists(collection_path), f"File not exists: {collection_path}"
        self.con = sqlite3.connect(collection_path)
        self.root_deck_name = root_deck_name
        self.cats_df = cats_df
        self.cards_df = cards_df
        # 是否插入 "未分类" deck
        self.insert_default_deck = False
        for idx, row in self.cards_df.items():
            if row['aid'] == 0:
                self.insert_default_deck = True
                break
        self.tpls_df = tpls_df

    def close(self):
        self.con.close()

    def clear_old_rows(self):
        with self.con as c:
            c.execute("DELETE FROM cards")
            c.execute("DELETE FROM notes")
            c.execute("DELETE FROM revlog")
            c.execute("DELETE FROM col")
            c.commit()

    @staticmethod
    def modify_model_for_choices(model):
        tmpl = model['tmpls'][0]
        tmpl['qfmt'] = re.sub(r"\[choice:(.*?)]",
                              r'<div class="choice-option" data-opt="\1" onclick="onChoice(this)">\1. {{\1}}</div>',
                              tmpl['qfmt'])
        tmpl['qfmt'] += """
        <script>
    window.GF_ans = "{{answer}}"
    window.GF_options = {}
    window.GF_isMulti = window.GF_ans.length > 1
    if (window.GF_isMulti) {
        $(".select-type-tips").addClass("checkbox")
    }
    var optE = $("[data-opt=E]")
    if (optE.text().trim().length == 2) {
        // Hide empty option E
        optE.hide()
    }
    function onChoice(obj){
        var opt = $(obj).attr('data-opt')
        if (window.GF_options[opt] !== 1) {
            if (!window.GF_isMulti) {
                window.GF_options = {}
                $(".choice-option").removeClass("select")
            }
            window.GF_options[opt] = 1
            $(obj).addClass("select")
        } else {
            window.GF_options[opt] = 0
            $(obj).removeClass("select")
        }
        console.log("window.GF_options", window.GF_options)
    }
</script>
        """

        tmpl['afmt'] = re.sub(r"\[choice:(.*?)]", r'<div class="choice-option" data-opt="\1">\1. {{\1}}</div>',
                              tmpl['afmt'])
        tmpl['afmt'] = tmpl['afmt'].replace('{{yourChoices}}', '<span class="yourChoices"></span>')
        tmpl['afmt'] += """
          <script>
    window.GF_options = window.GF_options || {}
    window.GF_ans = "{{answer}}"
    window.GF_isMulti = window.GF_ans.length > 1
    if (window.GF_isMulti) {
        $(".select-type-tips").addClass("checkbox")
    }
    var optE = $("[data-opt=E]")
    if (optE.text().trim().length == 2) {
        // Hide empty option E
        optE.hide()
    }
    var yourChoices = ""
    $(".choice-option").each(function(idx, obj) {
        var opt = $(obj).attr('data-opt')
        var isAnswer = window.GF_ans.indexOf(opt) > -1
        var isSelected = window.GF_options[opt] === 1
        if (isAnswer && isSelected) {
            $(obj).addClass("correct")
        } else if (isAnswer && !isSelected) {
            $(obj).addClass("correct-not-selected")
        } else if (!isAnswer && isSelected) {
            $(obj).addClass("error")
        } else if (!isAnswer && !isSelected) {
        }
        if (isSelected) {
            yourChoices += opt
        }
    })
    $(".yourChoices").text(yourChoices)
</script>
        """
        # Fix default .card's center align, which is ignored by jihu
        model['css'] += """.card {
    text-align: inherit!important;
}
"""
        model['css'] = re.sub(r"\./(.*?\.png)", r'_\1', model['css'])
        # class answer to GF_answer, to avoid conflict with Anki
        model['css'] = re.sub(r"\.answer", '.GF_answer', model['css'])
        tmpl['afmt'] = tmpl['afmt'] \
            .replace("class='answer", "class='GF_answer") \
            .replace("class=\"answer", "class=\"GF_answer")

    def get_decks(self):
        def get_deck_name(idx, child_name=None):
            """recursively build the deck name"""
            row = self.cats_df[idx]
            deck_name = row['name'] if child_name is None else f"{row['name']}::{child_name}"
            if row['pid'] == 0:
                return self.root_deck_name + "::" + deck_name
            else:
                return get_deck_name(row['pid'], deck_name)

        decks = {}
        for idx, row in self.cats_df.items():
            deck_info = deepcopy(BASE_DECK)
            deck_info['id'] = idx
            deck_info['name'] = get_deck_name(idx)
            decks[str(idx)] = deck_info
        if self.insert_default_deck or len(decks) == 0:
            # 添加一个默认目录
            deck_info = deepcopy(BASE_DECK)
            deck_info['id'] = DEFAULT_DECK_ID
            deck_info['name'] = self.root_deck_name
            decks[str(DEFAULT_DECK_ID)] = deck_info
        return decks

    @staticmethod
    def process_tmpl(tmpl: str):
        return str(tmpl).replace("{{@", "{{")

    def get_models(self):
        models = {}
        for idx, row in self.tpls_df.items():
            model = deepcopy(BASE_MODEL)
            model['name'] = row['name']
            model['css'] += row['css']
            for ord, f in enumerate(row['fields']):
                field = deepcopy(BASE_FIELD)
                field['name'] = f['name']
                field['ord'] = ord
                model['flds'].append(field)
            tmpl = deepcopy(BASE_TMPL)
            if "填空" in row['name']:
                tmpl['qfmt'] = self.process_tmpl(row['front']).replace("{{问题}}", "{{cloze:问题}}")
                tmpl['afmt'] = self.process_tmpl(row['back']).replace("{{问题}}", "{{cloze:问题}}")
            else:
                tmpl['qfmt'] = self.process_tmpl(row['front'])
                tmpl['afmt'] = self.process_tmpl(row['back'])
            model['tmpls'].append(tmpl)

            # handle double-sided cards
            if len(row['front_back'].strip()) > 0:
                model2 = deepcopy(BASE_MODEL)
                model2['name'] = row['name'] + "_back"
                model2['css'] += row['css_back']
                # XXX: use N+1 as back's model id
                model2['id'] = str(idx + 1)
                for ord, f in enumerate(row['fields']):
                    field = deepcopy(BASE_FIELD)
                    field['name'] = f['name']
                    field['ord'] = ord
                    model2['flds'].append(field)
                tmpl = deepcopy(BASE_TMPL)
                tmpl['qfmt'] = self.process_tmpl(row['front_back'])
                tmpl['afmt'] = self.process_tmpl(row['back_back'])
                model2['tmpls'].append(tmpl)
                models[str(idx + 1)] = model2

            if '[choice:A]' in model['tmpls'][0]['qfmt']:
                # 处理选择题的特殊格式
                AnkiCollectionWriter.modify_model_for_choices(model)

            model['id'] = str(idx)
            models[str(idx)] = model
        return models

    def insert_col_table(self):
        models = self.get_models()
        decks = self.get_decks()
        conf = deepcopy(BASE_CONF)
        deck_id = int(next(iter(decks)))
        conf['activeDecks'] = [deck_id]
        conf['curDeck'] = deck_id
        conf['curModel'] = next(iter(models))

        with self.con as c:
            c.execute('INSERT INTO col (id, crt, mod, scm, ver, dty, usn, ls, conf, models, decks, dconf, tags)'
                      ' values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (1, now_sec(), now_ms(), now_ms(), SCHEMA_VERSION, 0, 0, 0,
                       # conf
                       json.dumps(conf),
                       json.dumps(models),
                       json.dumps(decks),
                       json.dumps(BASE_DCONF),
                       json.dumps(BASE_TAGS)
                       ))

            c.commit()

    def insert_fields_to_notes(self, idx, fields_dict, model):
        fields = []
        # insert fields according to static/anki-awesome-select.json
        if model['name'] == "AwesomeSelect-3.x":
            fields = [
                str(idx),  # id
                convert_to_apkg_format(fields_dict.get("question"))  # question
            ]
            # options
            options = []
            for field_name in fields_dict.keys():
                f = convert_to_apkg_format(fields_dict.get(field_name))
                if is_capital_letter(field_name):
                    options.append(f)
            fields.append("||".join(filter(lambda x: len(x) > 0, options)))

            # answer
            # convert to 1, 2, 3
            answer = fields_dict.get("answer") or ""
            answer_list = [str(ord(x) - ord("A") + 1) for x in answer]
            fields.append("||".join(answer_list))

            # notes
            fields.append(convert_to_apkg_format(fields_dict.get("explain")))
        else:
            # insert fields by default
            for field_name in [x['name'] for x in model['flds']]:
                f = convert_to_apkg_format(fields_dict.get(field_name))
                fields.append(f)
        return fields

    def insert_notes_table(self):
        models = self.get_models()

        cnt = 0
        with self.con as c:
            for idx, row in self.cards_df.items():
                # logger.info(f'Writing card {row}')

                # aid (cats id) as did
                deckId = row['aid']
                # “未分类”卡片，换成另外一个deck id
                if deckId == 0:
                    deckId = DEFAULT_DECK_ID
                cnt += 1
                tid = row['tid']
                model_id = tid
                if row['is_back'] == 1:
                    model_id += 1
                model = models[str(model_id)]
                fields_dict = row['data']
                fields = self.insert_fields_to_notes(idx, fields_dict, model)

                c.execute("INSERT INTO notes (id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data)"
                          " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (idx, gen_guid(), model_id, now_sec(), -1, '',
                           # flds
                           '\x1f'.join(fields),
                           fields[0],
                           # fake csum
                           random.randint(0, 1000000),
                           0, ''
                           ))
                c.execute(
                    "INSERT INTO cards (id, nid, did, ord, mod, usn, type, queue, due, ivl, factor, reps, lapses, left, odue, odid, flags, data)"
                    " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (idx, idx,  # same cid, did
                     deckId,
                     0,  # ord
                     now_sec(),
                     -1, 0, 0,
                     cnt,  # from 1 as due
                     0, 0, 0, 0, 0, 0, 0, 0,
                     ''
                     ))
            c.commit()
