# This class isn't used in the tests
# It is just a solution so devs can see what the expected output is
class Person:
    def __init__(self, name, age, weight, married, mother=None, father=None):
        self.name = name
        self.age = age
        self.weight = weight
        self.married = married
        self.mother = mother
        self.father = father

    def __eq__(self, other):
        if not isinstance(other, Person):
            return False

        if (
            self.name != other.name
            or self.age != other.age
            or self.weight != other.weight
            or self.married != other.married
        ):
            return False

        if bool(self.mother) != bool(other.mother) or bool(self.father) != bool(
            other.father
        ):
            return False

        if self.mother and not self.mother.__eq__(other.mother):
            return False

        if self.father and not self.father.__eq__(other.father):
            return False

        return True

    @classmethod
    def load_data(cls, file_path):
        import json

        with open(file_path, "r") as file:
            data = json.load(file)
        people = []
        for person_data in data["People"]:
            if "parents" in person_data and "children" in person_data:
                parents = [cls(**parent_data) for parent_data in person_data["parents"]]
                children = [
                    cls(mother=parents[0], father=parents[1], **child_data)
                    for child_data in person_data["children"]
                ]
                people.extend(parents)
                people.extend(children)
            else:
                people.append(cls(**person_data))
        return people
