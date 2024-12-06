
# Oemof Industry

Holds the `MultiInputMultiOutputConverter` for modeling industrial components.

## Introduction

The features in this repo were developed for the SEDOS project:

* `MultiInputMultiOutputConverter` (MIMOConverter)
* `MIMO` facade
* `CO2EmissionLimit`

The MIMOConverter is designed to handle multiple inputs and multiple outputs, enabling advanced modeling of
industrial components with the oemof framework.
The `MIMO` facade simplifies the use of the MIMOConverter with [`oemof.tabular`](https://github.com/oemof/oemof-tabular), which loads oemof energy systems from tabular data sources.
Additionally, `CO2EmissionLimit` is provided to add an emission constraint to an energy system based on CO2, CH4 and N2O emissions. This also includes negative CO2 emissions.

## Installation
To install *oemof.industry* follow these steps:

* Clone *oemof.industry*  `git clone https://github.com/sedos-project/oemof.industry.git`
* enter folder `cd oemof.industry`
* create virtual environment using conda: `conda env create -f environment.yml`
* activate environment: `conda activate oemof.industry`
* install oemof.instry package using poetry, via: `poetry install`

## Development

To run the all tests run:

    pytest

## Usage
To use oemof.industry features in a project:

    from oemof_industry.mimo_converter import MultiInputMultiOutputConverter, MIMO
    from oemof_industry. emission_constraint import CO2EmissionLimit

Checkout the docstring examples ([mimo_converter](https://github.com/sedos-project/oemof.industry/blob/main/oemof_industry/mimo_converter.py), [emission_constraint](https://github.com/sedos-project/oemof.industry/blob/main/oemof_industry/emission_constraint.py)) and the [tests](https://github.com/sedos-project/oemof.industry/tree/main/tests) to get an overview on how to use the components.

#### MIMO and multi-period optimization
The mimo component was tested with a multi-period optimization of a [steel industry](https://github.com/sedos-project/steel_industry) secenario. 
For processing results of a multi-period optimization containing mimos you have to drop the mimo groups from the model results.
A quick fix to that is adding the following line to oemof.solph.processing [here](https://github.com/oemof/oemof-solph/blob/v0.5.2.dev1/src/oemof/solph/processing.py#L241).

    df_dict = {key: value for key, value in df_dict.items() if type(key[1]) != str}

## Contributing

You are warmly welcome to contribute to this repository. If you notice a bug please open an [issue](https://github.com/sedos-project/oemof.industry/issues/new).
If you like to contribute code go ahead an open a pull request, we are happy to review it. 

