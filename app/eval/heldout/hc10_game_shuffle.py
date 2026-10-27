import random


def new_deck():
    return [(rank, suit) for suit in "SHDC" for rank in range(1, 14)]


def shuffled_deck():
    deck = new_deck()
    random.shuffle(deck)
    return deck


def deal(deck, hands, size):
    return [[deck.pop() for _ in range(size)] for _ in range(hands)]
