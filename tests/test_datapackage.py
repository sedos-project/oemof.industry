import pathlib
import pytest

from oemof.solph import EnergySystem, Model, processing
from oemof.tabular import datapackage  # noqa

# from oemof.tabular.postprocessing import calculations
from oemof.tabular.facades import Bus, Commodity, Conversion, Excess, Load

from oemof_industry.mimo_converter import MIMO, MultiInputMultiOutputConverterBlock


class TestMimoFacade:
    # @classmethod
    # def setup_class(cls):


    @classmethod
    def setup_method(cls):
        MIMO_DATAPACKAGE = (
                pathlib.Path(
                    # __file__).parent / "datapackages" / "mimo" / "exo_steel" / "datapackage.json"
                    __file__).parent / "datapackages" / "mimo" / "IIS_CHPSTMGAS101_LB" / "datapackage.json"
        )
        TYPEMAP = {
            "bus": Bus,
            "commodity": Commodity,
            "conversion": Conversion,
            "excess": Excess,
            "load": Load,
            "mimo": MIMO,
        }
        cls.es = EnergySystem.from_datapackage(
            str(MIMO_DATAPACKAGE), attributemap={}, typemap=TYPEMAP
        )

    def test_model_structure(self):# todo note: test with "exo_steel"

        for mimo in self.es.groups[MultiInputMultiOutputConverterBlock]:  # todo - how to use `set`

            # "gas" is input group
            group_names = [input for input in mimo.input_groups.keys()]
            assert "gas" in group_names

            # check the group's buses (labels)
            group_bus_labels = [bus.label for bus in
                                mimo.input_groups["gas"].keys()]
            assert group_bus_labels == ["sec_H2", "ch4"]

            # check input buses
            input_buses = list(mimo.input_groups.values())[1:]
            input_labels = [list(bus.keys())[0].label for bus in input_buses]
            assert input_labels == ["electricity", "sec_coke_oven_gas", "iip_steel_crudesteel", "sec_H2", "ch4"]

            # check output buses (no groups)
            output_buses = list(mimo.output_groups.values())
            output_labels = [list(bus.keys())[0].label for bus in output_buses]
            assert output_labels == ["exo_steel", "co2_em", "ch4_em", "n2o_em"]  # todo fails

            # check other parameters
            assert mimo.conversion_factors["gas"].default == 5
            # assert mimo.conversion_factors["sec_coke_oven_gas"].default == 2.2  # todo
            # assert mimo.conversion_factors["electricity"].default == 0.3

    def test_results_IIS_CHPSTMGAS101_LB(self):  # todo note: test with IIS_CHPSTMGAS101_LB
        m = Model(self.es)
        m.solve("cbc")

        # create result object
        results = processing.convert_keys_to_strings(processing.results(m))

        assert results[("gas", "mimo")]["sequences"]["flow"].values[
                   0
               ] == pytest.approx(5.4945, abs=1e-3)
        assert results[("gas", "mimo")]["sequences"]["flow"].values[
                   1
               ] == pytest.approx(0)
        assert results[("hydro", "mimo")]["sequences"]["flow"].values[
                   0
               ] == pytest.approx(5.4945, abs=1e-2)
        assert results[("hydro", "mimo")]["sequences"]["flow"].values[
                   1
               ] == pytest.approx(10.8696, abs=1e-3)
        assert results[("mimo", "ch4_em")]["sequences"]["flow"].values[
                   0] == pytest.approx(
            0.0149, abs=1e-3
        )
        assert results[("mimo", "ch4_em")]["sequences"]["flow"].values[
                   1] == pytest.approx(
            0.0148, abs=1e-3
        )
        assert results[("mimo", "co2_em")]["sequences"]["flow"].values[
                   0] == pytest.approx(
            307.6923, abs=1e-2
        )
        assert results[("mimo", "co2_em")]["sequences"]["flow"].values[
                   1] == pytest.approx(
            0
        )

    def test_solving_and_postprocessing(self):
        m = Model(self.es)

        # if you want dual variables / shadow prices uncomment line below
        # m.receive_duals()

        # select solver 'gurobi', 'cplex', 'glpk' etc
        m.solve("cbc")

        # Groups have to be excluded, otherwise processing tries to merge them to
        # component sequences resulting in an index error due to non-matching lengths of entries
        self.es.params = processing.parameter_as_dict(self.es, exclude_attrs=["group"])
        self.es.results = m.results()

        # Not working due to MIMO Group Flows not filtered in postprocessing.
        # As the pyomo tuples of those variables are holding node, group_name, period
        # and timeindex and period and timeindex are not removed, like it is done for
        # Flow Vars, this leads to an error
        # (ValueError: Length of names must match number of levels in MultiIndex) in
        # `Calculator` class in `oemof.tabular.postprocessing.core` when Multiindex is
        # set from oemof_tuple.

        # -> We have to adapt tabulars postprocessing in order to get rid of this error
        # Maybe only in private branch, as this is caused by custom facade MIMO.

        # postprocessed_results = calculations.run_postprocessing(self.es)
        # postprocessed_results.to_csv("./results.csv")
