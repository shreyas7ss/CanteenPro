Update the Mini Website Navigation & Ordering Flow

Redesign the mini website to provide a fast, intuitive, and minimal-click ordering experience for a college canteen.

---

Home Screen

When the customer opens the mini website, display only the food categories.

Example categories:

- 🍛 Non-Veg Curry Items
- 🍗 Chicken Starters
- 🍳 Breakfast & Snacks
- 🍚 Rice Items
- 🥤 Beverages
- 🍰 Desserts

At the bottom of the screen, display a Cart section and a Checkout button.

Initially:

- Cart should be empty.
- Checkout should remain disabled until at least one item has been added.

---

Category Selection

When the customer selects a category (for example, Breakfast & Snacks), display only the food items belonging to that category.

Each food item should display:

- Food Name
- Price
- Add to Cart button

Example:

Masala Dosa
₹60

[ Add to Cart ]

---

Add to Cart Behavior

When the customer taps Add to Cart:

1. Immediately add the selected item to the shopping cart.
2. Display a short confirmation such as:
   - "Masala Dosa added to cart."
3. Automatically return the customer to the Home Screen (Category Menu).
4. The Cart section at the bottom should instantly update.

The cart preview should display only the names of the selected items.

Example:

🛒 Cart

* Masala Dosa
* Tea
* Chicken Roll

[ Checkout ]

The customer can continue selecting more categories and adding more items.

---

Cart

The cart shown on the Home Screen is only a quick preview.

It should display:

- Selected item names
- Number of selected items

It does not need to display prices or quantities at this stage.

---

Checkout

When the customer taps Checkout:

Open a final Order Review page.

This page should display the complete order details, including:

- Item names
- Quantity of each item
- Individual item prices
- Subtotal for each item
- Grand Total

Example:

Order Summary

Masala Dosa ×2
₹60 × 2 = ₹120

Tea ×1
₹15

Chicken Roll ×1
₹80

--------------------
Total = ₹215

This is the only page where prices and quantities are fully shown.

---

Complete Order

When the customer confirms the order:

1. Finalize the order.
2. Close the mini website.
3. Return the customer to the Telegram chat.

The Telegram bot should immediately send:

- Complete order summary
- Total amount
- Pay Now button using a UPI Deep Link ("upi://pay?...")

After completing payment, the customer returns to Telegram and taps I've Paid.

For the prototype, the backend will treat this as a successful payment, generate the token number, update the dashboard, and notify the customer.

---

Desired User Flow

1. Open Mini Website.
2. View food categories.
3. Select a category.
4. Select a food item.
5. Tap Add to Cart.
6. Automatically return to the Category Menu.
7. Cart preview updates with the selected item.
8. Repeat for any other categories.
9. Tap Checkout.
10. Review the complete order summary with prices and quantities.
11. Confirm the order.
12. Exit the mini website.
13. Receive the payment message in Telegram.
14. Complete payment and receive the order token.

---

Goal

The ordering experience should be extremely fast and require as few taps as possible. Customers should focus on selecting food quickly, while the detailed bill is shown only once during checkout. This keeps the interface clean, simple, and optimized for college students ordering during short break times.

make a todo and build it

#changes

1.remove checkout options while choosing an item 
2.include item wise quantity even in the cart of the main page
3.after confrimorder with payment also add cancel order option
