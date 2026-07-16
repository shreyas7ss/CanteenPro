from dataclasses import dataclass


@dataclass
class CartItem:
    menu_item_id: str
    item_name: str
    unit_price: float
    quantity: int


_carts: dict[int, dict[str, CartItem]] = {}


def get_cart(telegram_user_id: int) -> dict[str, CartItem]:
    return _carts.setdefault(telegram_user_id, {})


def add_item(telegram_user_id: int, menu_item_id: str, item_name: str, unit_price: float) -> None:
    cart = get_cart(telegram_user_id)
    if menu_item_id in cart:
        cart[menu_item_id].quantity += 1
    else:
        cart[menu_item_id] = CartItem(menu_item_id, item_name, unit_price, 1)


def clear_cart(telegram_user_id: int) -> None:
    _carts.pop(telegram_user_id, None)


def cart_total(telegram_user_id: int) -> float:
    return sum(item.unit_price * item.quantity for item in get_cart(telegram_user_id).values())
