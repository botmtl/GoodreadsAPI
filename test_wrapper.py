import datetime
from lxml import etree, objectify
from lxml.etree import Element
import re
from urllib2 import urlopen



class _LXMLWrapper(object):
    def __init__(self, response):
        self.parsed_response = objectify.fromstring(response)

    def to_string(self):
        """Convert Item XML to string.

        :return:
            A string representation of the Item xml.
        """
        return etree.tostring(self.parsed_response, pretty_print=True)

    def _safe_get_element(self, path, root=None):
        """Safe Get Element.

        Get a child element of root (multiple levels deep) failing silently
        if any descendant does not exist.

        :param root:
            Lxml element.
        :param path:
            String path (i.e. u'Items.Item.Offers.Offer').
        :return:
            Element or None.
        """
        elements = path.split(u'.')
        parent = root if root is not None else self.parsed_response
        for element in elements[:-1]:
            parent = getattr(parent, element, None)
            if parent is None:
                return None
        return getattr(parent, elements[-1], None)

    def _safe_get_element_text(self, path, root=None):
        # type: (Element, (unicode or None)) -> unicode or None
        """Safe get element text.

        Get element as string or None,
        :rtype: Text or None
        :param root: Lxml element.
        :param path: String path (i.e. u'Items.Item.Offers.Offer').
        :return: unicode or None
        """
        element = self._safe_get_element(path, root)
        if element is not None and hasattr(element, 'text') and element.text is not None:
            if isinstance(element.text, str) or isinstance(element.text, unicode):
                return element.text.strip()
        else:
            return None

    def _safe_get_element_date(self, path, root=None):
        """Safe get elemnent date.

        Get element as datetime.date or None,
        :param root:
            Lxml element.
        :param path:
            String path (i.e. u'Items.Item.Offers.Offer').
        :return:
            datetime.date or None.
        """
        value = self._safe_get_element_text(path=path, root=root)
        if value is not None:
            try:
                from datetime import datetime
                value = datetime.strptime(value, u'%Y-%m-%d')
                if value:
                    value = value.date()
            except ValueError:
                value = None

        return value


class _GoodreadsBook(_LXMLWrapper):
    """A wrapper class for an BottlenoseAmazon product.
    """

    def __init__(self, item, tags_threshold):
        self.tags_threshold = tags_threshold
        super(_GoodreadsBook, self).__init__(item)

    @property
    def title(self):
        # type: () -> unicode
        return self._safe_get_element_text('book.title')

    @property
    def authors(self):
        return [author.name.text for author in self._safe_get_element('book.authors.author')]

    @property
    def asin(self):
        return self._safe_get_element_text('book.kindle_asin') or self._safe_get_element_text('book.asin')

    @property
    def isbn(self):
        # type: () -> unicode
        """
        :return: unicode: isbn
        """
        return self._safe_get_element_text('book.isbn13') or self._safe_get_element_text('book.isbn')

    @property
    def id(self):
        return self._safe_get_element_text('book.id')

    @property
    def image_url(self):
        return self._safe_get_element_text('book.image_url')

    @property
    def publisher(self):
        return self._safe_get_element_text('book.publisher')

    @property
    def comments(self):
        return self._safe_get_element_text('book.description')

    @property
    def average_rating(self):
        return self._safe_get_element_text('book.average_rating')

    @property
    def tags(self):
        return [shelf.attrib['name'] for shelf in self._safe_get_element('book.popular_shelves.shelf') if
                int(shelf.attrib['count']) >= self.tags_threshold]

    @property
    def series(self):
        return self._safe_get_element_text('book.series_works.series_work.series.title')

    @property
    def series_index(self):
        return self._safe_get_element_text('book.series_works.series_work.user_position')

    @property
    def num_pages(self):
        return self._safe_get_element_text('book.num_pages')

    @property
    def pubdate(self):
        year = self._safe_get_element_text('book.work.original_publication_year')
        month = self._safe_get_element_text('book.work.original_publication_month')
        day = self._safe_get_element_text('book.work.original_publication_day')
        if year and month and day:
            return  datetime.date(int(year), int(month), int(day))
        return None



response=urlopen('https://www.goodreads.com/book/isbn/6977769.xml?key=f9c3KJCkdBVktDF6WuCy3w').read()
book = _GoodreadsBook(response, 1)
print(book.title)
print(book.authors)
print(book.comments)
print(book.isbn)
print(book.num_pages)
print(book.pubdate)
print(book.publisher)
print(book.series)
print(book.series_index)