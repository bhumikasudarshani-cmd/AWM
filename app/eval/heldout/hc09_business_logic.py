def apply_discount(price, customer):
    if customer.years > 5:
        return price * 0.9
    if customer.years > 2:
        return price * 0.95
    return price


def order_total(items, customer):
    subtotal = sum(item.price * item.qty for item in items)
    return round(apply_discount(subtotal, customer), 2)


def group_by_category(items):
    groups = {}
    for item in items:
        groups.setdefault(item.category, []).append(item)
    return groups
