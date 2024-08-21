import pathlib
import pytest
import pandas as pd
import warnings

from oemof.solph import EnergySystem, Model, processing
from oemof.tabular import datapackage  # noqa
from oemof.tabular.facades import Conversion, Load, Bus, Commodity, Excess

from oemof_industry.mimo_converter import MIMO
from tests.test_mimo_converter import check_results_for_IIS_CHPSTMGAS101_LB
from oemof_industry.emission_constraint import (CONSTRAINT_TYPE_MAP,
                                                CO2EmissionLimit)

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

    termination_condition = m.solver_results["Solver"][0]["Termination condition"]
    assert termination_condition != "infeasible"

    results = processing.convert_keys_to_strings(processing.results(m))
    check_results_for_IIS_CHPSTMGAS101_LB(results)

    co2_eq = (
        results[("mimo", "INDCO2N")]["sequences"]["flow"].sum()
        + 28 * results[("mimo", "INDCH4N")]["sequences"]["flow"].sum()
        + 265 * results[("mimo", "INDN2ON")]["sequences"]["flow"].sum()
    )

    assert co2_eq <= 360


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

    # add emission constraint with low co2 limit to make problem infeasible
    emission_constraint = CO2EmissionLimit(
        type="co2_emission_limit",
        co2_limit=10,
        ch4_factor=28,
        n2o_factor=265,
        commodities={
            "co2_commodities": ["INDCO2N"],
            "ch4_commodities": ["INDCH4N"],
            "n2o_commodities": ["INDN2ON"]
        }
    )
    emission_constraint.build_constraint(m)

    m.solve(solver="cbc")

    termination_condition = m.solver_results["Solver"][0]["Termination condition"]
    assert termination_condition == "infeasible"
