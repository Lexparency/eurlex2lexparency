from lxml import etree as et
from eurlex2lexparency.utils.xtml import unfold


# TODO: Include caching for some queries, e.g. number of rows.
class HtmlTable(object):
    # TODO: Handle the restructuring of the tables into list-items via this class.
    def __init__(self, element):
        assert et.iselement(element)
        assert element.tag == 'table'
        self.table = element
        self.body = self.table.find('tbody')
        if self.body is None:
            self.body = self.table
        self.colgroup = self.table.find('colgroup')
        if self.colgroup is None and self.table.find('./col') is not None:
            self.table.insert(0, et.Element('colgroup'))
            for col in self.table.xpath('./col'):
                self.table[0].append(col)
            self.colgroup = self.table[0]
        self.head = self.table.find('thead')
        self.foot = self.table.find('tfoot')

    @property
    def single_celled(self):
        if self.head is None and self.foot is None:
            if len(self.body.xpath('./tr')) == 1:
                return len(self.body.xpath('./tr/td')) == 1
            else:
                return False
        return False

    def unfold(self):
        if et.iselement(self.colgroup):
            self.table.remove(self.colgroup)
        for part in (self.head, self.body, self.foot):
            if part is None:
                continue
            for row in part.xpath('./tr'):
                for cell in row.xpath('./td'):
                    unfold(cell)
                unfold(row)
            unfold(part)
        if self.body != self.table:
            unfold(self.table)

    def convert_hidden_list_to_list(self):
        columns = self.count_columns()
        rows = self.count_rows()
        # It's a hidden list if either of the two cases are true:
        if columns == 1 and rows > 2:
            self.convert_to_unnumbered_list(wise='row')
        if rows == 1 and columns > 2:
            self.convert_to_unnumbered_list(wise='column')

    def is_column_empty(self, column):
        for table_part in [self.head, self.body, self.foot]:
            if table_part is not None:
                for row in table_part.iterchildren('tr'):
                    if et.tostring(row[column], method='text', encoding='unicode').strip() != ''\
                            or row[column].xpath('.//img'):
                        return False
        return True

    def is_equation_array(self):
        if len(self.body.find('tr')) != 3 or self.head is not None or self.foot is not None:
            return False
        for row in self.body.xpath('./tr'):
            if et.tostring(row[1], method='text', encoding='unicode').strip() != '=':
                return False
        return True

    def convert_to_unnumbered_list(self, wise='row'):
        if self.head is not None or self.foot is not None:
            return
        if self.colgroup is not None:
            self.table.remove(self.colgroup)
        for col_element in self.table.xpath('.//col'):
            col_element.getparent().remove(col_element)
        if wise == 'row':
            for row in self.body:
                for column in row.xpath('td'):
                    for pseudo_paragraph in column.xpath('p'):
                        unfold(pseudo_paragraph)
                    unfold(column)
                row.tag = 'li'
                for key in row.attrib:
                    row.attrib.pop(key)
        else:
            columns = self.count_columns()  # TODO: Exist a possibility to use previously calculated values
            for col_number in range(columns):
                active_item = et.SubElement(self.body, 'li')
                for row in self.body.xpath('./tr'):
                    active_item.append(row.xpath('./td')[0])
                for table_data in active_item.xpath('./td'):
                    unfold(table_data)
            for row in self.body.xpath('./tr'):
                self.body.remove(row)
        if self.body.tag == 'tbody':
            unfold(self.body)
        self.table.tag = 'ul'
        for key in self.table.attrib:
            self.table.attrib.pop(key)
        self.table.attrib['class'] = wise

    def remove_column(self, column):
        for table_part in [self.head, self.body, self.foot, self.colgroup]:
            if table_part is not None:
                for row in table_part.xpath('tr'):
                    row.remove(row[column])
                if table_part.tag == 'colgroup':
                    table_part.remove(table_part[column])

    def count_columns(self):
        return len(self.body.find('tr'))

    def count_rows(self):
        row_number = len(self.body)
        if self.head is not None:
            row_number += len(self.head)
        if self.foot is not None:
            row_number += len(self.foot)
        return row_number

    def textify(self, row):
        return '\t'.join([et.tostring(cell, method='text', encoding='unicode').strip()
                          for cell in self.body[row].iterchildren()])

    def remove(self, *parts):
        for part in parts:
            if getattr(self, part) is not None:
                self.table.remove(getattr(self, part))

    def attach(self, attachment):
        attachment_handler = HtmlTable(attachment)
        for row in attachment_handler.body.xpath('./tr'):
            self.body.append(row)
        attachment.getparent().remove(attachment)

    def convert_pseudo_table_to_list_item(self):
        # TODO: This function should not be part of this class definition.
        # TODO:   Instead, it should be closer to the class that is using it.
        assert len(self.body[0]) == 2
        # remove colgroup element
        # lift content of <tr> element to the <table> level.
        # reset attributes of table: class=...
        active_element = self.body[0][1]
        # Deep-copy is not what I actually want. otherwise, it would reinsert the tables.
        assert active_element.tag == 'td'
        active_element.tag = 'li'
        active_element.attrib.clear()
        active_element.attrib['data-title'] = et.tostring(self.body[0][0], method='text', encoding='unicode').strip(" \n\t\r")
        self.table.getparent().replace(self.table, active_element)


if __name__ == '__main__':
    test_table = et.fromstring("""<table width="100%" border="0" cellspacing="0" cellpadding="0">
<col width="10%"/><col width="5%"/><col width="85%"/>
<tr><td valign="top">
    <p class="norm">C<span class="subscript">i</span>
    </p>
    </td>
    <td valign="top">
    <p class="norm">=</p>
    </td>
    <td valign="top">
    <p class="norm">concentration of component i (weight percentage);</p>
    </td>
    </tr>
</table>
""")
    handled_table = HtmlTable(test_table)
    handled_table.convert_hidden_list_to_list()
    # print(et.tostring(handled_table.table, encoding='unicode', pretty_print=True))
    print(handled_table.is_equation_array())
