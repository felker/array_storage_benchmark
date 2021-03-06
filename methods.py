
import gzip
from base64 import urlsafe_b64encode, urlsafe_b64decode
from genericpath import getsize
from os import fsync, remove
from pickle import dump as pkl_dump, load as pkl_load
from time import time
from fortranfile import FortranFile
from json_tricks import dump as jt_dump, load as jt_load
from numpy import array_equal, savetxt, loadtxt, frombuffer, save as np_save, load as np_load, savez_compressed, array
from pandas import read_stata, DataFrame, read_html, read_excel
from scipy.io import savemat, loadmat
from imgarray import save_array_img, load_array_img


def sync(fh):
	"""
	This makes sure data is written to disk, so that buffering doesn't influence the timings.
	"""
	fh.flush()
	fsync(fh.fileno())


class TimeArrStorage(object):
	extension = 'data'
	
	def __init__(self, reps=100):
		self.save_time = None
		self.load_time = None
		self.storage_space = None
	
	def __str__(self):
		return self.__class__.__name__
	
	def save(self, arr, pth):
		# implementations have to call `sync`!
		raise NotImplementedError
	
	def load(self, pth):
		raise NotImplementedError
	
	def time_save(self, arr, pth):
		t0 = time()
		self.save(arr, pth)
		self.save_time = time() - t0
		self.storage_space = getsize(pth)
	
	def time_load(self, ref_arr, pth):
		t0 = time()
		arr = self.load(pth)
		sm = arr.sum()  # this is necessary to make sure it isn't lazy-loaded
		self.load_time = time() - t0
		remove(pth)
		assert array_equal(arr, ref_arr), 'load failed for {0:}'.format(self)
		return sm
	

class Csv(TimeArrStorage):
	def save(self, arr, pth):
		with open(pth, 'w+') as fh:
			savetxt(fh, arr, delimiter=',')
			sync(fh)
	
	def load(self, pth):
		with open(pth, 'r') as fh:
			return loadtxt(fh, delimiter=',')


class CsvGzip(TimeArrStorage):
	def save(self, arr, pth):
		with gzip.open(pth, 'w+') as fh:
			savetxt(fh, arr, delimiter=',')
			sync(fh)
		
	def load(self, pth):
		with gzip.open(pth, 'r') as fh:
			return loadtxt(fh, delimiter=',')


class JSON(TimeArrStorage):
	def save(self, arr, pth):
		jt_dump(arr, pth, force_flush=True)
		
	def load(self, pth):
		return jt_load(pth)


class JSONGzip(TimeArrStorage):
	def save(self, arr, pth):
		jt_dump(arr, pth, compression=True, force_flush=True)
		
	def load(self, pth):
		return jt_load(pth)


class Binary(TimeArrStorage):
	def save(self, arr, pth):
		with open(pth, 'wb+') as fh:
			fh.write(b'{0:s} {1:d} {2:d}\n'.format(arr.dtype, *arr.shape))
			fh.write(arr.data)
			sync(fh)

	def load(self, pth):
		with open(pth, 'rb') as fh:
			dtype, w, h = str(fh.readline()).split()
			return frombuffer(fh.read(), dtype=dtype).reshape((int(w), int(h)))


class BinaryGzip(TimeArrStorage):
	def save(self, arr, pth):
		with gzip.open(pth, 'wb+') as fh:
			fh.write(b'{0:s} {1:d} {2:d}\n'.format(arr.dtype, *arr.shape))
			fh.write(arr.data)
			sync(fh)

	def load(self, pth):
		with gzip.open(pth, 'rb') as fh:
			dtype, w, h = str(fh.readline()).split()
			return frombuffer(fh.read(), dtype=dtype).reshape((int(w), int(h)))


class Pickle(TimeArrStorage):
	def save(self, arr, pth):
		with open(pth, 'wb+') as fh:
			pkl_dump(arr, fh)
			sync(fh)

	def load(self, pth):
		with open(pth, 'rb') as fh:
			return pkl_load(fh)


class PickleGzip(TimeArrStorage):
	def save(self, arr, pth):
		with gzip.open(pth, 'wb+') as fh:
			pkl_dump(arr, fh)
			sync(fh)

	def load(self, pth):
		with gzip.open(pth, 'rb') as fh:
			return pkl_load(fh)


class NPY(TimeArrStorage):
	extension = 'npy'
	def save(self, arr, pth):
		with open(pth, 'wb+') as fh:
			np_save(fh, arr, allow_pickle=False)
			sync(fh)
		
	def load(self, pth):
		return np_load(pth)


class NPYCompr(TimeArrStorage):
	extension = 'npz'
	def save(self, arr, pth):
		with open(pth, 'wb+') as fh:
			savez_compressed(fh, data=arr)
			sync(fh)
		
	def load(self, pth):
		return np_load(pth)['data']


class PNG(TimeArrStorage):
	def save(self, arr, pth):
		with open(pth, 'wb+') as fh:
			save_array_img(arr, pth, img_format='png')
			sync(fh)
			
	def load(self, pth):
		return load_array_img(pth)


class b64Enc(TimeArrStorage):
	def save(self, arr, pth):
		with open(pth, 'w+') as fh:
			fh.write(b'{0:s} {1:d} {2:d}\n'.format(arr.dtype, *arr.shape))
			fh.write(urlsafe_b64encode(arr.data))
			sync(fh)

	def load(self, pth):
		with open(pth, 'r') as fh:
			dtype, w, h = str(fh.readline()).split()
			return frombuffer(urlsafe_b64decode(fh.read()), dtype=dtype).reshape((int(w), int(h)))


class FortUnf(TimeArrStorage):
	# this implementation assumes float64
	def save(self, arr, pth):
		with FortranFile(pth, mode='wb+') as fh:
			for k in range(arr.shape[0]):
				fh.writeReals(arr[k, :], prec='d')
			sync(fh)

	def load(self, pth):
		rows = []
		with FortranFile(pth, mode='rb') as fh:
			try:
				while True:
					row = fh.readReals(prec='d')
					rows.append(row)
			except IOError:
				pass
		return array(rows)


class MatFile(TimeArrStorage):
	extension = 'mat'
	def save(self, arr, pth):
		with open(pth, 'w+') as fh:
			savemat(fh, dict(data=arr))
			sync(fh)

	def load(self, pth):
		with open(pth, 'r') as fh:
			return loadmat(fh)['data']


class Stata(TimeArrStorage):
	# converts to and from DataFrame since it's a pandas method
	extension = 'sta'
	def save(self, arr, pth):
		with open(pth, 'wb+') as fh:
			colnames = tuple('c{0:03d}'.format(k) for k in range(arr.shape[1]))
			DataFrame(data=arr, columns=colnames).to_stata(fh)
			# sync(fh)  # file handle already closed

	def load(self, pth):
		with open(pth, 'rb') as fh:
			data = read_stata(fh)
			return data.as_matrix(columns=data.columns[1:])


class HTML(TimeArrStorage):
	def save(self, arr, pth):
		print(arr.dtype, arr.shape)
		print(arr)
		with open(pth, 'w+') as fh:
			colnames = tuple('c{0:03d}'.format(k) for k in range(arr.shape[1]))
			DataFrame(data=arr, columns=colnames).to_html(fh, float_format=TODO, index=False)
			sync(fh)

	def load(self, pth):
		with open(pth, 'r') as fh:
			data = read_html(fh)[0]
			arr = data.as_matrix()#columns=data.columns[1:])
			print(arr.dtype, arr.shape)
			print(arr)
			return arr


class Excel(TimeArrStorage):
	def save(self, arr, pth):
		print(arr)
		with open(pth, 'w+') as fh:
			colnames = tuple('c{0:03d}'.format(k) for k in range(arr.shape[1]))
			DataFrame(data=arr, columns=colnames).to_excel(fh, sheet_name='data', index=False)
			sync(fh)

	def load(self, pth):
		with open(pth, 'r') as fh:
			data = read_excel(fh, sheetname='data')
			print(data.as_matrix(columns=data.columns[1:]))
			return data.as_matrix()



#todo: pandas formats - http://pandas.pydata.org/pandas-docs/stable/io.html
# hdf5
# sql

#todo: hdf5 - http://stackoverflow.com/a/9619713/723090

#todo: bloscpack http://stackoverflow.com/a/22225337/723090

#todo: pytables


METHODS = (Csv, CsvGzip, JSON, JSONGzip, HTML, b64Enc, Excel, Pickle, PickleGzip, Binary, BinaryGzip, NPY, NPYCompr, PNG, FortUnf, MatFile) #todo: Stata
METHODS = (Csv, CsvGzip, JSON, JSONGzip, b64Enc, Pickle, PickleGzip, Binary, BinaryGzip, NPY, NPYCompr, PNG, FortUnf, MatFile) #todo: Stata
#html
#excel
#stata

