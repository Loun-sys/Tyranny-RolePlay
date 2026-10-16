"""One consumable per inventory row; materials and sigils can still stack."""
CONSUMABLE_CATEGORIES = frozenset({'Расходуемые предметы', 'Зелья', 'Еда'})
STACKABLE_CATEGORIES = frozenset({'Материалы', 'Сигилы'})


def prepared_consumable(item):
    return (str(item.get('equipped_slot') or '').startswith('Быстрый предмет ')
            and int(item.get('quantity', 0)) == 1)


async def split_consumable_stacks(connection):
    """Keep the original ID/slot and every copy, including over-capacity bags."""
    rows = await connection.execute_fetchall(
        "SELECT inventory.* FROM inventory JOIN item_catalog ON item_catalog.id=item_id "
        "WHERE category IN ('Расходуемые предметы','Зелья','Еда') AND quantity>1")
    for row in rows:
        await connection.execute('UPDATE inventory SET quantity=1 WHERE id=?', (row['id'],))
        await connection.executemany('INSERT INTO inventory(character_id,item_id,quantity,notes) VALUES(?,?,1,?)',
                                    [(row['character_id'], row['item_id'], row['notes'])] * (row['quantity'] - 1))
    return len(rows)


SINGLE_CONSUMABLE_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS single_consumable_insert BEFORE INSERT ON inventory
WHEN NEW.quantity>1 AND EXISTS(SELECT 1 FROM item_catalog WHERE id=NEW.item_id
 AND category IN ('Расходуемые предметы','Зелья','Еда'))
BEGIN SELECT RAISE(ABORT,'Один расходник занимает один слот.'); END;
CREATE TRIGGER IF NOT EXISTS single_consumable_update BEFORE UPDATE OF quantity,item_id ON inventory
WHEN NEW.quantity>1 AND EXISTS(SELECT 1 FROM item_catalog WHERE id=NEW.item_id
 AND category IN ('Расходуемые предметы','Зелья','Еда'))
BEGIN SELECT RAISE(ABORT,'Один расходник занимает один слот.'); END;
"""
