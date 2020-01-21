# Licensed under a 3-clause BSD style license - see LICENSE.rst
import copy
import collections.abc
import yaml
from pathlib import Path
import astropy.units as u
from gammapy.modeling import Parameter, Parameters
from gammapy.utils.scripts import make_path

__all__ = ["Model", "SkyModels"]


class Model:
    """Model base class."""

    def __init__(self, **kwargs):
        # Copy default parameters from the class to the instance
        self._parameters = self.__class__.default_parameters.copy()
        for parameter in self._parameters:
            if parameter.name in self.__dict__:
                raise ValueError(
                    f"Invalid parameter name: {parameter.name!r}."
                    f"Attribute exists already: {getattr(self, parameter.name)!r}"
                )

            setattr(self, parameter.name, parameter)

        # Update parameter information from kwargs
        for name, value in kwargs.items():
            if name not in self.parameters.names:
                raise ValueError(
                    f"Invalid argument: {name!r}. Parameter names are: {self.parameters.names}"
                )

            self._parameters[name].quantity = u.Quantity(value)

    def __init_subclass__(cls, **kwargs):
        # Add parameters list on the model sub-class (not instances)
        cls.default_parameters = Parameters(
            [_ for _ in cls.__dict__.values() if isinstance(_, Parameter)]
        )

    def _init_from_parameters(self, parameters):
        """Create model from list of parameters.

        This should be called for models that generate
        the parameters dynamically in ``__init__``,
        like the ``NaimaSpectralModel``
        """
        # TODO: should we pass through `Parameters` here? Why?
        parameters = Parameters(parameters)
        self._parameters = parameters
        for parameter in parameters:
            setattr(self, parameter.name, parameter)

    @property
    def parameters(self):
        """Parameters (`~gammapy.modeling.Parameters`)"""
        return self._parameters

    def copy(self):
        """A deep copy."""
        return copy.deepcopy(self)

    def __str__(self):
        return f"{self.__class__.__name__}\n\n{self.parameters.to_table()}"

    def to_dict(self):
        """Create dict for YAML serialisation"""
        return {"type": self.tag, "parameters": self.parameters.to_dict()["parameters"]}

    @classmethod
    def from_dict(cls, data):
        params = {
            x["name"].split("@")[0]: x["value"] * u.Unit(x["unit"])
            for x in data["parameters"]
        }

        # TODO: this is a special case for spatial models, maybe better move to `SpatialModel` base class
        if "frame" in data:
            params["frame"] = data["frame"]

        model = cls(**params)
        model._update_from_dict(data)
        return model

    # TODO: try to get rid of this
    def _update_from_dict(self, data):
        self._parameters.update_from_dict(data)
        for parameter in self.parameters:
            setattr(self, parameter.name, parameter)

    @staticmethod
    def create(tag, *args, **kwargs):
        """Create a model instance.

        Examples
        --------
        >>> from gammapy.modeling import Model
        >>> spectral_model = Model.create("PowerLaw2SpectralModel", amplitude="1e-10 cm-2 s-1", index=3)
        >>> type(spectral_model)
        gammapy.modeling.models.spectral.PowerLaw2SpectralModel
        """
        from . import MODELS

        cls = MODELS.get_cls(tag)
        return cls(*args, **kwargs)


class SkyModels(collections.abc.Sequence):
    """Sky model collection.

    Parameters
    ----------
    skymodels : `SkyModel`, list of `SkyModel` or `SkyModels`
        Sky models
    """

    def __init__(self, skymodels):
        if isinstance(skymodels, SkyModels):
            models = skymodels._skymodels
        elif isinstance(skymodels, SkyModel):
            models = [skymodels]
        elif isinstance(skymodels, list):
            models = skymodels
        else:
            raise TypeError(f"Invalid type: {skymodels!r}")

        unique_names = []
        for model in models:
            if model.name in unique_names:
                raise (ValueError("SkyModel names must be unique"))
            unique_names.append(model.name)

        self._skymodels = models

    @property
    def parameters(self):
        return Parameters.from_stack([_.parameters for _ in self._skymodels])

    @property
    def names(self):
        return [m.name for m in self._skymodels]

    @classmethod
    def read(cls, filename):
        """Read from YAML file."""
        yaml_str = Path(filename).read_text()
        return cls.from_yaml(yaml_str)

    @classmethod
    def from_yaml(cls, yaml_str):
        """Create from YAML string."""
        from gammapy.modeling.serialize import dict_to_models

        data = yaml.safe_load(yaml_str)
        skymodels = dict_to_models(data)
        return cls(skymodels)

    def write(self, path, overwrite=False):
        """Write to YAML file."""
        path = make_path(path)
        if path.exists() and not overwrite:
            raise IOError(f"File exists already: {path}")
        path.write_text(self.to_yaml())

    def to_yaml(self):
        """Convert to YAML string."""
        from gammapy.modeling.serialize import models_to_dict

        data = models_to_dict(self._skymodels)
        return yaml.dump(
            data, sort_keys=False, indent=4, width=80, default_flow_style=None
        )

    def __str__(self):
        str_ = f"{self.__class__.__name__}\n\n"

        for idx, skymodel in enumerate(self):
            str_ += f"Component {idx}: {skymodel}\n\n\t\n\n"

        return str_

    def __add__(self, other):
        if isinstance(other, (SkyModels, list)):
            return SkyModels([*self, *other])
        elif isinstance(other, (SkyModel, SkyDiffuseCube)):
            return SkyModels([*self, other])
        else:
            raise TypeError(f"Invalid type: {other!r}")

    def __getitem__(self, val):
        if isinstance(val, int):
            return self._skymodels[val]
        elif isinstance(val, str):
            for idx, model in enumerate(self._skymodels):
                if val == model.name:
                    return self._skymodels[idx]
            raise IndexError(f"No model: {val!r}")
        else:
            raise TypeError(f"Invalid type: {type(val)!r}")

    def __len__(self):
        return len(self._skymodels)
