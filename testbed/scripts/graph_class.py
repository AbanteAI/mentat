# refactor to node class
# add bfs
# make dfs and bfs start from specific node
# make dfs and bfs return path
# check for empty graph
# make constructor take adjacency matrix
# make undirected graph
# refactor name to directed graph


class Graph:
    def __init__(self, values, connections):
        self.values = values
        self.connections = connections

    def dfs(self, goal):
        to_visit = [0]
        while to_visit:
            cur_node = to_visit.pop()
            if self.values[cur_node] == goal:
                return cur_node
            for adj in self.connections[cur_node]:
                to_visit.append(adj)
        return -1


def main():
    data = [5, 2, 8, 0, 3]
    connections = [[1, 2, 3], [0, 4], [0, 3], [0, 2], [0, 1]]
    graph = Graph(data, connections)
    print(graph.dfs(3))
    print(graph.dfs(9))


if __name__ == "__main__":
    main()
