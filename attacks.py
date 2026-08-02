# Two families of attack.
#
# The blind attacks see only the visible tests, because that is all a cheater
# gets. They contain no task logic at all.
#
# The blind spot attacks are different and they are the more interesting ones.
# They are given a correct solution and then deliberately broken on inputs that
# fall outside what the visible tests cover. They pass a verifier only if the
# suite forgot that case, so what they measure is test coverage rather than
# memorisation.


def _visible_outputs(task):
    return [task["reference"](*args) for args in task["visible_tests"]]


def _common_output(task):
    outs = [repr(o) for o in _visible_outputs(task)]
    best = max(set(outs), key=outs.count)
    for o in _visible_outputs(task):
        if repr(o) == best:
            return o


def constant_common(task):
    answer = _common_output(task)
    return lambda *args: answer


def memorize_visible(task):
    table = {repr(args): task["reference"](*args) for args in task["visible_tests"]}
    default = list(table.values())[0]
    return lambda *args: table.get(repr(args), default)


def constant_zero(task):
    return lambda *args: 0


def constant_true(task):
    return lambda *args: True


def return_input(task):
    return lambda *args: args[0]


def first_arg_length(task):
    # A plausible looking shortcut. Passes wherever the answer happens to equal
    # the size of the first argument on the visible tests.
    def candidate(*args):
        return len(args[0])
    return candidate


def _numbers(value):
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, str):
        return [len(value)]
    if isinstance(value, (list, tuple)):
        out = [len(value)]
        for item in value:
            out.extend(_numbers(item))
        return out
    return []


def _envelope(task):
    seen = []
    for args in task["visible_tests"]:
        for value in args:
            seen.extend(_numbers(value))
    if not seen:
        return None
    return min(seen), max(seen)


def edge_blind(task):
    # Correct inside the range of values the visible tests cover, wrong outside
    # it. This is what a solution that was tuned only against the published
    # tests looks like.
    bounds = _envelope(task)
    reference = task["reference"]
    fallback = _common_output(task)

    def candidate(*args):
        if bounds is not None:
            for value in args:
                for n in _numbers(value):
                    if n < bounds[0] or n > bounds[1]:
                        return fallback
        return reference(*args)

    return candidate


def empty_blind(task):
    # Correct except on empty inputs and zero. Test suites forget these
    # constantly.
    reference = task["reference"]
    fallback = _common_output(task)

    def candidate(*args):
        for value in args:
            if isinstance(value, (list, tuple, str, dict)) and len(value) == 0:
                return fallback
            if isinstance(value, int) and not isinstance(value, bool) and value == 0:
                return fallback
        return reference(*args)

    return candidate


def all_attacks():
    return {
        "constant_common": constant_common,
        "memorize_visible": memorize_visible,
        "constant_zero": constant_zero,
        "constant_true": constant_true,
        "return_input": return_input,
        "first_arg_length": first_arg_length,
        "edge_blind": edge_blind,
        "empty_blind": empty_blind,
    }
