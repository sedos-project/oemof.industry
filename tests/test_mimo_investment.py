# -*- coding: utf-8 -*-
"""
Example that illustrates how to use component `MultiInputMultiOutputConverter`.

SPDX-License-Identifier: MIT
"""
import pandas as pd
import pytest
from oemof.solph import EnergySystem, Investment, Model, processing
from oemof.solph.buses import Bus
from oemof.solph.components import Sink, Source
from oemof.solph.flows import Flow

from oemof_industry.mimo_converter import MultiInputMultiOutputConverter


def test_too_many_investments():
    b_gas = Bus(label="gas")
    b_hydro = Bus(label="hydro")
    b_electricity = Bus(label="electricity", balanced=False)
    b_heat = Bus(label="heat", balanced=True)
    b_heat_low = Bus(label="heat_low", balanced=False)

    with pytest.raises(ValueError, match="Only one investment allowed."):
        MultiInputMultiOutputConverter(
            label="mimo",
            inputs={"in": {b_gas: Flow(nominal_value=Investment(ep_costs=1.2, maximum=20)), b_hydro: Flow()}},
            outputs={
                b_electricity: Flow(nominal_value=Investment(ep_costs=1.2, maximum=20)),
                "heat": {b_heat: Flow(), b_heat_low: Flow()},
            },
            conversion_factors={b_gas: 1.2, b_hydro: 1.3, b_heat: 1.2},
            flow_shares={"fix": {b_gas: [0.8, 0.3], b_heat: 0.8}},
        )


def test_investment_fix_outputs():
    idx = pd.date_range("1/1/2017", periods=2, freq="H")
    es = EnergySystem(timeindex=idx)

    # resources
    b_gas = Bus(label="gas")
    es.add(b_gas)
    es.add(Source(label="gas_station", outputs={b_gas: Flow(variable_costs=2)}))

    b_hydro = Bus(label="hydro")
    es.add(b_hydro)
    es.add(Source(label="hydro_station", outputs={b_hydro: Flow(variable_costs=3)}))

    b_electricity = Bus(label="electricity", balanced=False)
    es.add(b_electricity)

    b_heat = Bus(label="heat", balanced=True)
    es.add(b_heat)

    b_heat_low = Bus(label="heat_low", balanced=False)
    es.add(b_heat)

    es.add(Source(label="heat_import", outputs={b_heat: Flow(nominal_value=Investment(ep_costs=200), variable_costs=200)}))

    es.add(
        Sink(
            label="demand",
            inputs={b_heat: Flow(fix=[100, 80], nominal_value=1)},
        )
    )

    es.add(
        MultiInputMultiOutputConverter(
            label="mimo",
            inputs={"in": {b_gas: Flow(), b_hydro: Flow()}},
            outputs={
                b_electricity: Flow(nominal_value=Investment(ep_costs=1.2, maximum=20)),
                "heat": {b_heat: Flow(), b_heat_low: Flow()},
            },
            conversion_factors={b_gas: 1.2, b_hydro: 1.3, b_heat: 1.2},
            flow_shares={"fix": {b_gas: [0.8, 0.3], b_heat: 0.8}},
            activity_bounds={"max": 18}
        )
    )

    # create an optimization problem and solve it
    om = Model(es)

    # solve model
    om.solve(solver="cbc")

    # create result object
    results = processing.convert_keys_to_strings(processing.results(om))

    assert results[("mimo", "electricity")]["scalars"]["invest"] == 18

    assert results[("mimo", "heat")]["sequences"]["flow"].values[0] == 18 * 0.8 * 1.2
    assert results[("heat_import", "heat")]["sequences"]["flow"].values[0] == 100 - 18 * 0.8 * 1.2
    assert results[("mimo", "electricity")]["sequences"]["flow"].values[0] == 18


def test_investment_var_outputs():
    idx = pd.date_range("1/1/2017", periods=3, freq="H")
    es = EnergySystem(timeindex=idx)

    # resources
    b_gas = Bus(label="gas")
    es.add(b_gas)
    es.add(Source(label="gas_station", outputs={b_gas: Flow(variable_costs=2)}))

    b_hydro = Bus(label="hydro")
    es.add(b_hydro)
    es.add(Source(label="hydro_station", outputs={b_hydro: Flow(variable_costs=3)}))

    b_electricity = Bus(label="electricity", balanced=False)
    es.add(b_electricity)

    b_heat = Bus(label="heat")
    es.add(b_heat)

    es.add(Source(label="heat_import", outputs={b_heat: Flow(variable_costs=200)}))

    es.add(
        Sink(
            label="demand",
            inputs={b_heat: Flow(fix=[100, 100, 100], nominal_value=1)},
        )
    )

    es.add(
        MultiInputMultiOutputConverter(
            label="mimo",
            inputs={"in": {b_gas: Flow(), b_hydro: Flow()}},
            outputs={
                "out": {
                    b_electricity: Flow(nominal_value=Investment(ep_costs=1.2, maximum=20)),
                    b_heat: Flow()
                },
            },
            conversion_factors={b_gas: 1.2, b_hydro: 1.3, b_heat: 1.2},
            flow_shares={"fix": {b_gas: [0.8, 0.3, 0.3]}},
            activity_bounds={"max": 18}
        )
    )

    # create an optimization problem and solve it
    om = Model(es)

    # solve model
    om.solve(solver="cbc")

    # create result object
    results = processing.convert_keys_to_strings(processing.results(om))

    check_results_for_investment_var_output(results)


def check_results_for_investment_var_output(results):
    assert results[("mimo", "electricity")]["scalars"]["invest"] == 18
    assert results[("mimo", "heat")]["sequences"]["flow"].values[0] == pytest.approx(18 * 1.2)
    assert results[("heat_import", "heat")]["sequences"]["flow"].values[0] == pytest.approx(100 - 18 * 1.2)
    assert results[("mimo", "electricity")]["sequences"]["flow"].values[0] == 0

    assert results[("gas", "mimo")]["sequences"]["flow"].values[0] == pytest.approx(18 * 1.2 * 0.8)
    assert results[("hydro", "mimo")]["sequences"]["flow"].values[0] == pytest.approx(18 * 1.3 * 0.2)
