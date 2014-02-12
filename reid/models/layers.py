#!/usr/bin/python2
#-*- coding: utf-8 -*-

import numpy
import theano
import theano.tensor as T

from reid.models.block import Block
from reid.models import active_functions as actfuncs
from reid.utils import numpy_rng


class FullConnLayer(Block):
    """Fully connected layer"""

    def __init__(self, input_size, output_size, active_func=None,
                 W=None, b=None):
        super(FullConnLayer, self).__init__()

        self._active_func = active_func

        if W is None:
            W_bound = numpy.sqrt(6.0 / (input_size + output_size))

            if active_func == actfuncs.sigmoid: W_bound *= 4

            init_W = numpy.asarray(numpy_rng.uniform(
                low=-W_bound, high=W_bound,
                size=(input_size, output_size)), dtype=theano.config.floatX)

            self._W = theano.shared(value=init_W, borrow=True)
        else:
            self._W = W

        if b is None:
            init_b = numpy.zeros(output_size, dtype=theano.config.floatX)

            self._b = theano.shared(value=init_b, borrow=True)
        else:
            self._b = b

        self._params = [self._W, self._b]

    def get_output(self, x):
        z = T.dot(x, self._W) + self._b
        return z if self._active_func is None else self._active_func(z)

    def get_regularization(self, l):
        return self._W.norm(l)


class ConvPoolLayer(Block):
    """Convolutional and max-pooling layer"""

    def __init__(self, filter_shape, pool_shape,
                 image_shape=None, active_func=None, flatten_output=False):
        """Initialize the convolutional and max-pooling layer

        Args:
            filter_shape: 4D-tensor, (n_filters, n_channels, n_rows, n_cols)
            pool_shape: 2D-tensor, (n_rows, n_cols)
            image_shape: None if the input is always 4D-tensor, (n_images, 
                n_channels, n_rows, n_cols). If the input images are represented
                as vectors, then a 3D-tensor, (n_channels, n_rows, n_cols) is 
                required.
            active_func: Active function of this layer
            flatten_output: True if the output image should be flattened as a 
                vector.
        """

        super(ConvPoolLayer, self).__init__()

        self._filter_shape = filter_shape
        self._pool_shape = pool_shape
        self._image_shape = image_shape
        self._active_func = active_func
        self._flatten_output = flatten_output

        fan_in = numpy.prod(filter_shape[1:])
        fan_out = filter_shape[0] * numpy.prod(filter_shape[2:]) / numpy.prod(pool_shape)

        W_bound = numpy.sqrt(6.0 / (fan_in + fan_out))

        if active_func == actfuncs.sigmoid: W_bound *= 4

        init_W = numpy.asarray(numpy_rng.uniform(
            low=-W_bound, high=W_bound,
            size=filter_shape), dtype=theano.config.floatX)

        self._W = theano.shared(value=init_W, borrow=True)

        init_b = numpy.zeros((filter_shape[0],), dtype=theano.config.floatX)

        self._b = theano.shared(value=init_b, borrow=True)

        self._params = [self._W, self._b]

    def get_output(self, x):
        if self._image_shape is not None:
            x = x.reshape((x.shape[0],) + self._image_shape)

        z = T.nnet.conv.conv2d(
            input=x,
            filters=self._W,
            filter_shape=self._filter_shape)

        y = T.signal.downsample.max_pool_2d(
            input=z,
            ds=self._pool_shape,
            ignore_border=True)

        y = y + self._b.dimshuffle('x', 0, 'x', 'x')

        if self._active_func is not None:
            y = self._active_func(y)

        if self._flatten_output:
            y = y.flatten(2)

        return y

    def get_regulariation(self, l):
        return self._W.norm(l)


class CompLayer(Block):
    """Composition layer

    Composition layer combines a list of input data into a long vector
    """

    def get_output(self, x):
        """Get the combined vector

        Args:
            x: A list of theano symbols

        Returns:
            A long vector consisting of all the flattened input symbols
        """

        return T.concatenate([data.flatten() for data in x])
     

class DecompLayer(Block):
    """Decomposition layer

    Decomposition layer separates a long vector into a list of output data
    """

    def __init__(self, data_shapes):
        """Initialize the decomposition layer

        Args:
            data_shapes: A list of tuples representing shapes of each data
                sample
        """

        super(DecompLayer, self).__init__()

        self._data_shapes = data_shapes

        self._segments = [0]
        for i, shape in enumerate(data_shapes):
            self._segments.append(self._segments[i] + numpy.prod(shape))

    def get_output(self, x):
        """Get the separated list of data samples

        Args:
            x: A long numpy vector

        Returns:
            A list of data samples which are theano symbols
        """

        ret = []
        for i, shape in enumerate(self._data_shapes):
            l, r = self._segments[i], self._segments[i+1]
            ret.append(x[l:r].reshape(shape))

        return ret
