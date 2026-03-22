import pytest

from app.infrastructure.patterns.dependency_injection import DIContainer, get_container, inject


class Interface:
    pass


class Implementation(Interface):
    pass


class Dependency:
    pass


class ServiceWithDependency:
    def __init__(self, dep: Dependency):
        self.dep = dep


class ServiceWithDefault:
    def __init__(self, dep: Dependency = None):
        self.dep = dep


def test_register_class():
    container = DIContainer()
    container.register(Interface, Implementation)
    instance = container.resolve(Interface)
    assert isinstance(instance, Implementation)


def test_register_instance():
    container = DIContainer()
    instance = Implementation()
    container.register(Interface, instance)
    resolved = container.resolve(Interface)
    assert resolved is instance


def test_register_factory():
    container = DIContainer()
    container.register_factory(Interface, Implementation)
    instance = container.resolve(Interface)
    assert isinstance(instance, Implementation)


def test_register_singleton():
    container = DIContainer()
    instance = Implementation()
    container.register_singleton(Interface, instance)
    resolved = container.resolve(Interface)
    assert resolved is instance


def test_resolve_recursive_dependencies():
    container = DIContainer()
    container.register(Dependency, Dependency)
    container.register(ServiceWithDependency, ServiceWithDependency)

    service = container.resolve(ServiceWithDependency)
    assert isinstance(service, ServiceWithDependency)
    assert isinstance(service.dep, Dependency)


def test_resolve_unregistered_service_raises_error():
    container = DIContainer()
    with pytest.raises(ValueError, match="Service not registered"):
        container.resolve(Interface)


def test_resolve_missing_dependency_raises_error():
    container = DIContainer()
    container.register(ServiceWithDependency, ServiceWithDependency)
    # Dependency is NOT registered
    with pytest.raises(ValueError, match="Service not registered"):
        container.resolve(ServiceWithDependency)


def test_resolve_uses_default_value_if_missing():
    container = DIContainer()
    container.register(ServiceWithDefault, ServiceWithDefault)
    # Dependency is NOT registered, but it has a default value
    service = container.resolve(ServiceWithDefault)
    assert service.dep is None


def test_clear():
    container = DIContainer()
    container.register(Interface, Implementation)
    container.clear()
    with pytest.raises(ValueError, match="Service not registered"):
        container.resolve(Interface)


def test_get_container():
    container = get_container()
    assert isinstance(container, DIContainer)
    assert container is get_container()


def test_inject_decorator():
    container = get_container()
    container.clear()

    class DecoratedDependency:
        pass

    container.register(DecoratedDependency, DecoratedDependency)

    @inject
    def my_function(dep: DecoratedDependency):
        return dep

    result = my_function()
    assert isinstance(result, DecoratedDependency)

    # Test manual override
    manual_dep = DecoratedDependency()
    result_manual = my_function(dep=manual_dep)
    assert result_manual is manual_dep
