import pathlib
import pytest
import pandas as pd
import warnings

from oemof.solph import EnergySystem, Model, processing
from oemof.tabular import datapackage  # noqa
from oemof.tabular.facades import Conversion, Load, Bus, Commodity, Excess

from oemof_industry.mimo_converter import MIMO
from tests.test_mimo_converter import check_results_for_IIS_CHPSTMGAS101_LB
from oemof_industry.emission_constraint import CONSTRAINT_TYPE_MAP

TYPEMAP = {
    "bus": Bus,
    "commodity": Commodity,
    "conversion": Conversion,
    "excess": Excess,
    "load": Load,
    "mimo": MIMO,
}


def test_emission_constraint_IIS_CHPSTMGAS101_LB():
    datapackage_path = (
        pathlib.Path(__file__).parent
        / "datapackages"
        / "mimo"
        / "IIS_CHPSTMGAS101_LB"
        / "datapackage.json"
    )
    es = EnergySystem.from_datapackage(
        str(datapackage_path), attributemap={}, typemap=TYPEMAP
    )

    m = Model(es)
    m.add_constraints_from_datapackage(str(datapackage_path),
                                       constraint_type_map=CONSTRAINT_TYPE_MAP)

    m.solve(solver="cbc")
    results = processing.convert_keys_to_strings(processing.results(m))
    check_results_for_IIS_CHPSTMGAS101_LB(results)


def test_emission_constraint_IIS_CHPSTMGAS101_LB_infeasible():
    datapackage_path = (
        pathlib.Path(__file__).parent
        / "datapackages"
        / "mimo"
        / "IIS_CHPSTMGAS101_LB"
        / "datapackage.json"
    )
    es = EnergySystem.from_datapackage(
        str(datapackage_path), attributemap={}, typemap=TYPEMAP
    )

    m = Model(es)

    # manipulate co2 limit to make problem infeasible
    emi_path = (
        pathlib.Path(__file__).parent
        / "datapackages"
        / "mimo"
        / "IIS_CHPSTMGAS101_LB"
        / "data"
        / "constraints"
        / "emission_constraint.csv"
    )
    emission_constraint_orig = pd.read_csv(emi_path, sep=";", index_col=0)
    emission_constraint = emission_constraint_orig.copy()
    emission_constraint["co2_limit"] = 0
    emission_constraint.to_csv(emi_path, sep=";")

    m.add_constraints_from_datapackage(str(datapackage_path),
                                       constraint_type_map=CONSTRAINT_TYPE_MAP)
    # revoke chances in csv
    emission_constraint_orig.to_csv(emi_path, sep=";")

    with pytest.raises(RuntimeError):
        # turn warnings into errors  todo contribution to MVS
        warnings.filterwarnings("error")
        warnings.filterwarnings("always", category=FutureWarning)
        try:
            m.solve(solver="cbc")
            results = processing.convert_keys_to_strings(processing.results(m))
            check_results_for_IIS_CHPSTMGAS101_LB(results)
        except UserWarning as e:
            error_message = str(e)
            infeasible_msg = "termination condition infeasible"
            if infeasible_msg in error_message:
                raise RuntimeError(error_message) from None
            else:
                raise e
        # stop turning warnings into errors
        warnings.resetwarnings()
