import pandas as pd
from oemof.solph import helpers

from oemof import solph
from oemof.tabular.facades import Conversion
from oemof_industry.emission_constraint import CO2EmissionLimit


def test_emission_constraint():
    date_time_index = pd.date_range("1/1/2012", periods=3, freq="H")
    tmpdir = helpers.extend_basic_path("tmp")
    energysystem = solph.EnergySystem(
        groupings=solph.GROUPINGS, timeindex=date_time_index
    )
#
    bus_biomass = solph.Bus("biomass")
    bus_heat = solph.Bus("heat")
    bus_co2_em = solph.Bus("co2_em")
    bus_ch4_em = solph.Bus("ch4_em")

    conversion = Conversion(
        label="biomass_plant",
        carrier="biomass",
        tech="st",
        from_bus=bus_biomass,
        to_bus=bus_heat,
        emissions={bus_co2_em: 0.5, bus_ch4_em: 10},
        capacity=100,
        efficiency=0.4,
    )

    emission_constraint = CO2EmissionLimit(
        name="emission_constraint",
        type="co2_emission_limit",
        co2_limit=1000,
        ch4_equivalent=25,
        n2o_equivalent=298,
        co2_commodities=["co2_em"],
        ch4_commodities=["ch4_em"],
    )

    energysystem.add(bus_biomass, bus_heat, bus_co2_em, bus_ch4_em, conversion)
    model = solph.Model(energysystem)

    emission_constraint.build_constraint(model)

