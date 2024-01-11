# [collection(x) for x in collection] would be nice but trivial


def accumulate(collection, operation):
    response = []
    for ellement in collection:
        response.append(operation(ellement))
    return response
