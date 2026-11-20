from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from rest_framework.exceptions import ValidationError


def parse_int(request, name, default=None, minimum=None, maximum=None):
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({name: 'Must be an integer.'})
    if minimum is not None and value < minimum:
        raise ValidationError({name: f'Must be at least {minimum}.'})
    if maximum is not None and value > maximum:
        raise ValidationError({name: f'Must be at most {maximum}.'})
    return value


def parse_page(request, default=1):
    return parse_int(request, 'page', default=default, minimum=1)


def parse_page_size(request, default=20, maximum=100):
    return parse_int(request, 'page_size', default=default, minimum=1, maximum=maximum)


def paginate(object_list, page, page_size):
    """Paginate a queryset or list.

    Returns (page_items, meta) where meta contains count, next, previous,
    page_size, current_page, total_pages.
    """
    paginator = Paginator(object_list, page_size)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    meta = {
        'count': paginator.count,
        'next': page_obj.next_page_number() if page_obj.has_next() else None,
        'previous': page_obj.previous_page_number() if page_obj.has_previous() else None,
        'page_size': page_size,
        'current_page': page_obj.number,
        'total_pages': paginator.num_pages,
    }
    return list(page_obj.object_list), meta
