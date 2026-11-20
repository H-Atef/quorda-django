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


def parse_bool(request, name, default=None):
    raw = request.query_params.get(name)
    if raw is None:
        return default
    value = str(raw).lower()
    if value in ('true', '1', 'yes'):
        return True
    if value in ('false', '0', 'no'):
        return False
    raise ValidationError({name: 'Must be true or false.'})


def parse_is_indoor(request):
    """Parse is_indoor: None (both), True (dine-in), False (delivery)."""
    raw = request.query_params.get('is_indoor')
    if raw is None:
        return None
    value = str(raw).lower()
    if value in ('true', '1', 'yes'):
        return True
    if value in ('false', '0', 'no'):
        return False
    raise ValidationError({'is_indoor': 'Must be true or false.'})


def parse_scope(request, default='all'):
    """Parse scope: 'all', 'vip', or 'normal'."""
    raw = request.query_params.get('scope', default).lower()
    if raw not in ('all', 'vip', 'normal'):
        raise ValidationError({'scope': "Must be 'all', 'vip', or 'normal'."})
    return raw


def parse_statuses(request):
    """Parse comma-separated statuses, validate against Order.Status."""
    from apps.orders.models import Order
    raw = request.query_params.get('status')
    if raw is None:
        return None
    valid = set(Order.Status.values)
    statuses = [s.strip() for s in raw.split(',') if s.strip()]
    if not statuses:
        raise ValidationError({'status': 'Must include at least one status.'})
    invalid = [s for s in statuses if s not in valid]
    if invalid:
        raise ValidationError({
            'status': f'Invalid status value(s): {", ".join(invalid)}. Valid: {", ".join(sorted(valid))}.'
        })
    return statuses


def parse_limit(request):
    raw = request.query_params.get('limit')
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({'limit': 'Must be an integer.'})
    if value < 1:
        raise ValidationError({'limit': 'Must be at least 1.'})
    return value


def parse_window_size(request, default=10):
    return parse_int(request, 'window_size', default=default, minimum=1)


def parse_page(request, default=1):
    return parse_int(request, 'page', default=default, minimum=1)


def parse_page_size(request, default=20, maximum=100):
    return parse_int(request, 'page_size', default=default, minimum=1, maximum=maximum)


def parse_batch_limit(request, default=None):
    return parse_int(request, 'batch_limit', default=default, minimum=1)


def parse_ordering(request, default=None, allowed=None):
    raw = request.query_params.get('ordering', default)
    if raw is None:
        return None
    if allowed:
        fields = [f.lstrip('-') for f in raw.split(',')]
        invalid = [f for f in fields if f not in allowed]
        if invalid:
            raise ValidationError({
                'ordering': f'Invalid field(s): {", ".join(invalid)}. Allowed: {", ".join(sorted(allowed))}.'
            })
    return raw