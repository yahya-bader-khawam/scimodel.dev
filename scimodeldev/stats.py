# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd
import scipy.stats as stats
from scipy.stats import norm
import torch
import math
from torch.distributions import StudentT
from scipy.special import gammaln
import warnings
from statsmodels.stats.multicomp import pairwise_tukeyhsd


class SciModelStats:

  def __init__(self, device='cpu'):
    self.device = torch.device(device)

    # Create a more detailed z-score table
    self.z_values = torch.linspace(-3.5, 3.5, 7000).to(self.device)
    self.prob_values = 0.5 * (1 + torch.erf(self.z_values / math.sqrt(2))).to(self.device)

  def to_tensor(self, data):
    if isinstance(data, torch.Tensor):
      return data.to(self.device)

    elif isinstance(data, np.ndarray):
      return torch.from_numpy(data).to(self.device)

    elif isinstance(data, pd.DataFrame):
      return torch.from_numpy(data.values).to(self.device)

    elif isinstance(data, pd.Series):
      return torch.from_numpy(data.values).to(self.device)

    elif isinstance(data, float) or isinstance(data, int):
      return torch.tensor(data)

    elif isinstance(data, list):
      return torch.tensor(data)

    else:
      raise TypeError("Data type passed to the class is not supported.")

  def _isodd(self, num):
    if (num % 2) == 0:
      return False
    else:
      return True

  def mean(self, data):
    return torch.sum(data, dim=0) / data.shape[0]

  def median(self, data, interpolation='linear'):
    sorted_data, _ = torch.sort(data, dim=0)
    n = sorted_data.shape[0]

    if self._isodd(n):
      mid_val = int((n+1)/2)
      median_val = sorted_data[mid_val-1] # -1 because python index starts from 0s
    else:
      left_val = int(n/2)
      right_val = int((n/2)+1)

      if interpolation == 'lower':
        median_val = sorted_data[left_val-1] # -1 because python index starts from 0

      elif interpolation == 'higher':
        median_val = sorted_data[right_val-1] # -1 because python index starts from 0

      elif interpolation == 'midpoint':
        median_val = (sorted_data[right_val-1] + sorted_data[left_val-1])/2

      elif interpolation == 'linear':
        x0 = left_val-1
        y0 = sorted_data[x0]
        x1 = right_val-1
        y1 = sorted_data[x1]
        x = (x0+x1)/2
        y = y0 + (x - x0)*((y1-y0)/(x1-x0))
        median_val = y

      else:
        raise ValueError("Invalid interpolation type")

    return median_val

  def mode(self, data):
    values, counts = torch.unique(data, sorted=False, return_counts=True)
    max_count = torch.max(counts)
    return values[counts == max_count]

  def std(self, data, ddof=0): # delta degrees of freedom
    n = len(data)
    mu = self.mean(data)
    squared_diff = torch.sum(torch.pow(data - mu, 2), dim=0)
    variance = squared_diff / (n - ddof)
    std_dev = torch.sqrt(variance)
    return std_dev

  def range(self, data):
    return torch.max(data, dim=0).values - torch.min(data, dim=0).values

  def percentile(self, data, q, interpolation='linear'):
    if not 0 <= q <= 100:
      raise ValueError("percentile must be between 0 and 100")

    sorted_data, _ = torch.sort(data, dim=0)
    n = sorted_data.shape[0]
    k = (n-1)*(q/100) # kth percentile with -1 since python index starts from 0
    k_floor = math.floor(k)
    k_ceil = math.ceil(k)

    if interpolation == 'lower':
      return sorted_data[k_floor]
    elif interpolation == 'higher':
      return sorted_data[k_ceil]
    elif interpolation == 'midpoint':
      return (sorted_data[k_floor] + data[k_ceil]) / 2
    elif interpolation == 'linear':
      if k_floor == k_ceil:
        return sorted_data[int(k)]
      else:
        x = k
        x0 = k_floor
        y0 = sorted_data[x0]
        x1 = k_ceil
        y1 = sorted_data[x1]
        return y0 + (x - x0)*((y1-y0)/(x1-x0))

  def IQR(self, data, interpolation='linear'):
    Q1 = self.percentile(data, 25, interpolation)
    Q3 = self.percentile(data, 75, interpolation)
    return Q3-Q1, Q1, Q3

  def z_score(self, data):
    return torch.div(data - self.mean(data), self.std(data))

  def modified_z_score(self, data):
      med = self.median(data)
      mad = self.median(torch.abs(data - med))
      return 0.6745*torch.div(data - med, mad)

  def fp_skewness(self, data):
    n = torch.tensor(len(data))
    n_val = n/((n-1)*(n-2))
    sum_arg = torch.div(data-self.mean(data),self.std(data))
    sum_arg_3 = torch.pow(sum_arg,3)
    skewness = n_val*torch.sum(sum_arg_3, dim=0)
    return skewness

  def outliers_from_IQR(self, data, interpolation='linear'):
    # returns only outliers
    iqr, q1, q3 = self.IQR(data, interpolation=interpolation)
    lower_bound = q1 - 1.5*iqr
    upper_bound = q3 + 1.5*iqr
    is_outlier = torch.logical_or(data < lower_bound, data > upper_bound)
    if len(data.shape)==1:
      data = torch.reshape(data,(len(data),1))
      is_outlier = torch.reshape(is_outlier,(len(data),1))
    outliers = [data[:,k][is_outlier[:,k]] for k in range(data.shape[-1])]
    outlier_indices = torch.where(is_outlier == True)
    outlier_indices = list(zip(outlier_indices[0],outlier_indices[1]))
    return outliers, outlier_indices, is_outlier


  def outliers_from_z(self, data, threshold=3):
    z = self.z_score(data)
    lower_bound = -1*threshold
    upper_bound = threshold
    is_outlier = torch.logical_or(z < lower_bound, z > upper_bound)
    if len(data.shape)==1:
      data = torch.reshape(data,(len(data),1))
      is_outlier = torch.reshape(is_outlier,(len(data),1))
    outliers = [data[:,k][is_outlier[:,k]] for k in range(data.shape[-1])]
    outlier_indices = torch.where(is_outlier == True)
    outlier_indices = list(zip(outlier_indices[0],outlier_indices[1]))
    return outliers, outlier_indices, is_outlier


  def outliers_from_modified_z(self, data, threshold=3.5):
    mod_z = self.modified_z_score(data)
    lower_bound = -1*threshold
    upper_bound = threshold
    is_outlier = mod_z > upper_bound
    if len(data.shape)==1:
      data = torch.reshape(data,(len(data),1))
      is_outlier = torch.reshape(is_outlier,(len(data),1))
    outliers = [data[:,k][is_outlier[:,k]] for k in range(data.shape[-1])]
    outlier_indices = torch.where(is_outlier == True)
    outlier_indices = list(zip(outlier_indices[0],outlier_indices[1]))
    return outliers, outlier_indices, is_outlier

  def cdf(self, z, mu=0, sigma=1):
    cum = 0.5 * (1 + torch.erf((z - mu) / (sigma * torch.sqrt(torch.tensor(2.)))))
    return cum

  def expected_value(self, data, probs):
    if data.shape != probs.shape:
      raise TypeError('The shape of probability array does not match that of the data')
    mul = torch.multiply(data,probs)
    ev = torch.sum(mul,dim=0)
    return ev

  def rand_var_std(self, data, probs):
    if data.shape != probs.shape:
      raise TypeError('The shape of probability array does not match that of the data')
    mu = self.expected_value(data, probs)
    variance = torch.sum(torch.mul(torch.pow(data - mu,2), probs), dim=0)
    rv_std = torch.sqrt(variance)
    return rv_std

  def factorial(self, n):
    return torch.prod(torch.arange(1, n+1))

  def permutations(self, n, k):
    return torch.div(self.factorial(n),self.factorial(n-k))

  def combinations(self, n, k):
    return torch.div(self.factorial(n),self.factorial(k)*self.factorial(n-k))

  def binomial_prob(self, n, k, p):
    p = torch.tensor(p)
    comb = self.combinations(n,k)
    return torch.tensor(comb*torch.pow(p,k)*torch.pow(1-p,n-k))

  def binomial_dist(self, n, K, p):
    p = torch.tensor(p)
    dist_tensor = []
    for k in K:
      dist_tensor.append(self.binomial_prob(n,k,p))
    return torch.tensor(dist_tensor)

  def poisson_prob(self, L, k):
    L = torch.tensor(L)
    return torch.div(torch.mul(torch.pow(L,k),torch.exp(-L)),self.factorial(k))

  def poisson_dist(self, L, K):
    dist_tensor = []
    for k in K:
      dist_tensor.append(self.poisson_prob(L,k))
    return torch.tensor(dist_tensor)

  def geometric_prob(self, p, k):
    p = torch.tensor(p)
    return torch.mul(p,torch.pow(1-p,k-1))

  def geometric_dist(self, p, K):
    dist_tensor = []
    for k in K:
      dist_tensor.append(self.geometric_prob(p,k))
    return torch.tensor(dist_tensor)

  def geometric_ex(self,p):
    p = torch.tensor(p)
    return torch.div(1,p)

  def geometric_std(self,p):
    p = torch.tensor(p)
    return torch.sqrt(torch.div(1-p,torch.pow(p,2)))

  def z_score_lookup(self, given_prob):
    # Convert the given_prob to a torch.tensor if it's not already
    if not isinstance(given_prob, torch.Tensor):
      given_prob = torch.tensor(given_prob)

    # Find the two closest probability values in the table
    diffs = torch.abs(self.prob_values - given_prob)

    if max(diffs) == 0:
      min_diffs, min_idxs = torch.topk(diffs, 1, largest=False)
      # Get the corresponding z-scores
      z_score = self.z_values[min_idxs[0]]

    else:
      min_diffs, min_idxs = torch.topk(diffs, 2, largest=False)
      # Get the corresponding z-scores
      z1 = self.z_values[min_idxs[0]]
      z2 = self.z_values[min_idxs[1]]
      # Interpolate between the two z-scores
      z_score = z1 + (z2 - z1) * (given_prob - self.prob_values[min_idxs[0]]) / (self.prob_values[min_idxs[1]] - self.prob_values[min_idxs[0]])

    return z_score.item()  # Return as a standard Python number for convenience

  def ppf(self, p, mu=0, sigma=1):
    p = torch.tensor(p).to(device=self.device)
    mu = torch.tensor(mu).to(device=self.device)
    sigma = torch.tensor(sigma).to(device=self.device)

    # PPF (inverse CDF) of the standard normal distribution using inverse error function
    return mu + sigma*torch.sqrt(torch.tensor(2.0).to(self.device)) * torch.erfinv(2.0*p - 1.0)

  def z_test(self, x_bar, mu, sigma, n, alpha, test_type='two-tail'):

    # Calculate Z score
    z_score = (torch.tensor(x_bar) - torch.tensor(mu)) / (torch.tensor(sigma) / torch.sqrt(torch.tensor(n)))
    print(f'Z score: {z_score}')

    # Z critical based on the type of test
    if test_type == 'lower-tail':
        z_critical = self.z_score_lookup(1 - alpha)
        print(f'Critical Z-score for lower-tail test: {z_critical}')
    elif test_type == 'upper-tail':
        z_critical = self.z_score_lookup(alpha)
        print(f'Critical Z-score for upper-tail test: {z_critical}')
    elif test_type == 'two-tail':
        z_critical = self.z_score_lookup(1 - alpha/2)
        print(f'Critical Z-score for two-tail test: {z_critical}')
    else:
        raise ValueError('test_type must be "lower-tail", "upper-tail", or "two-tail"')

    # Test the hypothesis
    if test_type == 'two-tail':
        if torch.abs(z_score) > z_critical:
            print("Reject the null hypothesis for the two-tail test.")
        else:
            print("Fail to reject the null hypothesis for the two-tail test.")
    elif test_type == 'lower-tail':
        if z_score < -z_critical:
            print("Reject the null hypothesis for the lower-tail test.")
        else:
            print("Fail to reject the null hypothesis for the lower-tail test.")
    elif test_type == 'upper-tail':
        if z_score > z_critical:
            print("Reject the null hypothesis for the upper-tail test.")
        else:
            print("Fail to reject the null hypothesis for the upper-tail test.")

    return z_score, z_critical


  def t_pdf(self, x, df):

    # make sure that both variables tensors
    if not isinstance(x, torch.Tensor):
      x = torch.tensor(x)
    if not isinstance(df, torch.Tensor):
      df = torch.tensor(df)

    # make sure those varaibles are set in the right device
    x = x.to(self.device)
    df = df.to(self.device)
    Pi = torch.tensor(math.pi).to(self.device)

    # PDF of the t-distribution
    nom = torch.exp(torch.lgamma((df + 1.0) / 2.0) - torch.lgamma(df / 2.0))
    denom = math.sqrt(df * Pi) * (1.0 + (x ** 2) / df) ** ((df + 1.0) / 2.0)

    return nom / denom

  def t_cdf(self, t_value, df, num_points=2000000):
    if not isinstance(t_value, torch.Tensor):
      x = torch.tensor(t_value).to(self.device)
    if not isinstance(df, torch.Tensor):
      df = torch.tensor(df).to(self.device)

    # Define the range for integration
    x = torch.linspace(-13000, t_value, num_points).to(self.device)

    # Compute the approximate integral using the trapezoidal rule
    y = self.t_pdf(x, df)
    integral_approx = torch.trapz(y, x)

    return integral_approx

  def t_test(self, x_bar, mu, s, n, alpha, test_type='two-tail'):

    df = n - 1

    # t statistic
    t_value = (x_bar - mu) / (s / torch.sqrt(torch.tensor(n)))

    # p-value calculation based on the type of test
    if test_type == 'lower-tail':
        p_value = self.t_cdf(t_value, df)
    elif test_type == 'upper-tail':
        p_value = 1 - self.t_cdf(t_value, df)
    elif test_type == 'two-tail':
        p_value = 2 * (1 - self.t_cdf(torch.abs(t_value),df))
    else:
        raise ValueError('test_type must be "lower-tail", "upper-tail", or "two-tail"')

    # Check the results of the hypothesis tests
    if p_value < alpha:
        print(f'Null hypothesis is rejected for the {test_type} test')
    else:
        print(f'Null hypothesis is accepted for the {test_type} test')

    return t_value, p_value

  def one_proportion(self, p, p0, n, alpha, test_type='two-tail'):
    p = torch.tensor(p)
    p0 = torch.tensor(p0)
    n = torch.tensor(n)

    # Calculate Z score
    z_score = (p-p0)/torch.sqrt((p0*(1-p0))/(n))
    print(f'Z score: {z_score}')

    # Z critical based on the type of test
    if test_type == 'lower-tail':
        z_critical = self.z_score_lookup(1 - alpha)
        print(f'Critical Z-score for lower-tail test: {z_critical}')
    elif test_type == 'upper-tail':
        z_critical = self.z_score_lookup(alpha)
        print(f'Critical Z-score for upper-tail test: {z_critical}')
    elif test_type == 'two-tail':
        z_critical = self.z_score_lookup(1 - alpha/2)
        print(f'Critical Z-score for two-tail test: {z_critical}')
    else:
        raise ValueError('test_type must be "lower-tail", "upper-tail", or "two-tail"')

    # Test the hypothesis
    if test_type == 'two-tail':
        if torch.abs(z_score) > z_critical:
            print("Reject the null hypothesis for the two-tail test.")
        else:
            print("Fail to reject the null hypothesis for the two-tail test.")
    elif test_type == 'lower-tail':
        if z_score < -z_critical:
            print("Reject the null hypothesis for the lower-tail test.")
        else:
            print("Fail to reject the null hypothesis for the lower-tail test.")
    elif test_type == 'upper-tail':
        if z_score > z_critical:
            print("Reject the null hypothesis for the upper-tail test.")
        else:
            print("Fail to reject the null hypothesis for the upper-tail test.")

    return z_score, z_critical

  def chi_log_pdf(self, x, k):

    # move x and k to the specified device
    if not isinstance(k, torch.Tensor):
      k = torch.tensor(k).to(self.device)
    if not isinstance(x, torch.Tensor):
      x = torch.tensor(x).to(self.device) + 1e-10

    return (k / 2 - 1) * torch.log(x) - x / 2 - (k / 2) * torch.log(torch.tensor(2.)) - torch.lgamma(k / 2)

  def chi_cdf(self, x, k):
    if not isinstance(k, torch.Tensor):
      k = torch.tensor(k).to(self.device)
    if not isinstance(x, torch.Tensor):
      x = torch.tensor(x).to(self.device)

    # generate a range of values
    x_range = torch.linspace(0.3e-6, x, steps=40000000, device=self.device) +  1e-10

    # compute the pdf values for this range
    pdf_values = torch.exp(self.chi_log_pdf(x_range, k))


    # calculate CDF by integrating the PDF
    cdf_value = torch.trapz(pdf_values, x_range)

    return cdf_value

  def chi_square_test(self, s, sigma, n, alpha, test_type='two-tail'):
    s = torch.tensor(s).to(self.device)
    sigma = torch.tensor(sigma).to(self.device)
    alpha = torch.tensor(alpha).to(self.device)

    k = n - 1

    # chi-square statistic
    chi_value = (k * s**2)/(sigma**2)

    # p-value calculation based on the type of test
    if test_type == 'lower-tail':
        p_value = self.chi_cdf(chi_value, k)
    elif test_type == 'upper-tail':
        p_value = 1 - self.chi_cdf(chi_value, k)
    elif test_type == 'two-tail':
        left_tail = self.chi_cdf(chi_value, k)
        right_tail = 1 - self.chi_cdf(chi_value, k)
        p_value = 2 * min(left_tail, right_tail)
    else:
        raise ValueError('test_type must be "lower-tail", "upper-tail", or "two-tail"')

    # Check the results of the hypothesis tests
    if p_value < alpha:
        print(f'Null hypothesis is rejected for the {test_type} test')
    else:
        print(f'Null hypothesis is accepted for the {test_type} test')

    return chi_value, p_value

  def two_sample_z_test(self, x1_bar, x2_bar, sigma1, sigma2, n1, n2, alpha, test_type='two-tail'):

      # Convert input to tensors
      x1_bar = torch.tensor(x1_bar).to(self.device)
      x2_bar = torch.tensor(x2_bar).to(self.device)
      sigma1 = torch.tensor(sigma1).to(self.device)
      sigma2 = torch.tensor(sigma2).to(self.device)
      n1 = torch.tensor(n1).to(self.device)
      n2 = torch.tensor(n2).to(self.device)
      alpha = torch.tensor(alpha).to(self.device)


      # Calculate the Z score
      z_score = (x1_bar - x2_bar) / torch.sqrt((sigma1 ** 2 / n1) + (sigma2 ** 2 / n2))
      print(f'Z score: {z_score}')

      # Calculate the critical Z score based on the type of test
      normal_dist = torch.distributions.Normal(0, 1)

      # Z critical based on the type of test
      normal_dist = torch.distributions.Normal(0, 1)
      if test_type == 'lower-tail':
          z_critical = -normal_dist.icdf(1 - alpha)
          print(f'Critical Z-score for lower-tail test: {z_critical}')
      elif test_type == 'upper-tail':
          z_critical = normal_dist.icdf(1 - alpha)
          print(f'Critical Z-score for upper-tail test: {z_critical}')
      elif test_type == 'two-tail':
          z_critical = normal_dist.icdf(1 - alpha / 2)
          print(f'Critical Z-score for two-tail test: {z_critical}')
      else:
          raise ValueError('test_type must be "lower-tail", "upper-tail", or "two-tail"')

      # Test the hypothesis
      if test_type == 'two-tail':
          if torch.abs(z_score) > z_critical:
              print("Reject the null hypothesis for the two-tail test.")
          else:
              print("Fail to reject the null hypothesis for the two-tail test.")
      elif test_type == 'lower-tail':
          if z_score < z_critical:  # Note: z_critical is already negative
              print("Reject the null hypothesis for the lower-tail test.")
          else:
              print("Fail to reject the null hypothesis for the lower-tail test.")
      elif test_type == 'upper-tail':
          if z_score > z_critical:
              print("Reject the null hypothesis for the upper-tail test.")
          else:
              print("Fail to reject the null hypothesis for the upper-tail test.")

      return z_score, z_critical

  def two_sample_t_test(self, mean1, mean2, n1, n2, std1, std2, alpha=0.05, test_type="two-tail", equal_variances=False):

      # Convert input to tensors
      mean1 = torch.tensor(mean1).to(self.device)
      mean2 = torch.tensor(mean2).to(self.device)
      std1 = torch.tensor(std1).to(self.device)
      std2 = torch.tensor(std2).to(self.device)
      n1 = torch.tensor(n1).to(self.device)
      n2 = torch.tensor(n2).to(self.device)
      alpha = torch.tensor(alpha).to(self.device)

      if equal_variances:
          pooled_std = torch.sqrt(((n1 - 1) * std1 ** 2 + (n2 - 1) * std2 ** 2) / (n1 + n2 - 2))
          se = pooled_std * torch.sqrt(1 / n1 + 1 / n2)
          df = n1 + n2 - 2
      else:
          se = torch.sqrt((std1 ** 2 / n1) + (std2 ** 2 / n2))
          df = (std1 ** 2 / n1 + std2 ** 2 / n2) ** 2 / ((std1 ** 2 / n1) ** 2 / (n1 - 1) + (std2 ** 2 / n2) ** 2 / (n2 - 1))

      t_statistic = (mean1 - mean2) / se


      # Calculate the p-value
      if test_type == 'lower-tail':
          p_value = self.t_cdf(t_statistic, df)
      elif test_type == 'upper-tail':
          p_value = 1 - self.t_cdf(t_statistic, df)
      elif test_type == 'two-tail':
          p_value = 2 * (1 - self.t_cdf(torch.abs(t_statistic), df))
      else:
          raise ValueError('test_type must be "lower-tail", "upper-tail", or "two-tail"')

      # Determine whether to reject or fail to reject the null hypothesis
      if p_value < alpha:
        print('Reject the null hypothesis')
        return t_statistic, p_value
      else:
        print('Fail to reject the null hypothesis')
        return t_statistic, p_value

  def paired_t_test(self, sample_1, sample_2, alpha=0.05, test_type="two-tail"):

      # Convert input to tensors of floating point numbers
      sample_1 = torch.tensor(sample_1, dtype=torch.float).to(self.device)
      sample_2 = torch.tensor(sample_2, dtype=torch.float).to(self.device)


      # Calculate differences and its mean and standard deviation.
      differences = sample_1 - sample_2
      mean_difference = torch.mean(differences)
      std_difference = torch.std(differences, correction=1) # correction is ddof

      # calculate n and degrees of freedom
      n = torch.tensor(len(differences))
      df = n - 1

      t_statistic = mean_difference / (std_difference / torch.sqrt(n))

      # Calculate the p-value
      if test_type == 'lower-tail':
          p_value = self.t_cdf(t_statistic, df)
      elif test_type == 'upper-tail':
          p_value = 1 - self.t_cdf(t_statistic, df)
      elif test_type == 'two-tail':
          p_value = 2 * (1 - self.t_cdf(torch.abs(t_statistic), df))
      else:
          raise ValueError('test_type must be "lower-tail", "upper-tail", or "two-tail"')

      # Determine whether to reject or fail to reject the null hypothesis
      if p_value < alpha:
        print('Reject the null hypothesis')
        return t_statistic, p_value
      else:
        print('Fail to reject the null hypothesis')
        return t_statistic, p_value

  def two_proportion_test(self, p1, p2, n1, n2, alpha, test_type='two-tail', method='pooled',d=0):

    # Convert input to tensors
    p1 = torch.tensor(p1, dtype=torch.float).to(self.device)
    p2 = torch.tensor(p2, dtype=torch.float).to(self.device)
    n1 = torch.tensor(n1, dtype=torch.float).to(self.device)
    n2 = torch.tensor(n2, dtype=torch.float).to(self.device)
    d = torch.tensor(d, dtype=torch.float).to(self.device)
    alpha = torch.tensor(alpha, dtype=torch.float).to(self.device)

    # Z-score calculation
    if method == 'pooled':
        p_pooled = ((p1 * n1) + (p2 * n2)) / (n1 + n2)
        z_score = (p1 - p2) / torch.sqrt(p_pooled * (1 - p_pooled) * (1/n1 + 1/n2))
    elif method == 'unpooled':
        z_score = (p1 - p2 - d) / torch.sqrt(p1 * (1-p1) / n1 + p2 * (1-p2) / n2)
    else:
        raise ValueError("Method must be either 'pooled' or 'unpooled'")

    # Critical Z score based on the type of test
    normal_dist = torch.distributions.Normal(0, 1)
    if test_type == 'lower-tail':
        z_critical = -normal_dist.icdf(1 - alpha)
    elif test_type == 'upper-tail':
        z_critical = normal_dist.icdf(1 - alpha)
    elif test_type == 'two-tail':
        z_critical = normal_dist.icdf(1 - alpha / 2)
    else:
        raise ValueError('test_type must be "lower-tail", "upper-tail", or "two-tail"')

    # Test the hypothesis
    if test_type == 'two-tail':
        if torch.abs(z_score) > z_critical:
            print("Reject the null hypothesis for the two-tail test.")
        else:
            print("Fail to reject the null hypothesis for the two-tail test.")
    elif test_type == 'lower-tail':
        if z_score < z_critical:  # Note: z_critical is already negative
            print("Reject the null hypothesis for the lower-tail test.")
        else:
            print("Fail to reject the null hypothesis for the lower-tail test.")
    elif test_type == 'upper-tail':
        if z_score > z_critical:
            print("Reject the null hypothesis for the upper-tail test.")
        else:
            print("Fail to reject the null hypothesis for the upper-tail test.")

    return z_score, z_critical

  def F_pdf(self, x, d1, d2):

    if not torch.is_tensor(d1):
        d1 = torch.tensor(d1, dtype=torch.float).to(self.device)
    else:
        d1 = d1.float().to(self.device)

    if not torch.is_tensor(d2):
        d2 = torch.tensor(d2, dtype=torch.float).to(self.device)
    else:
        d2 = d2.float().to(self.device)

    log_numerator = 0.5 * d1 * torch.log(d1 * x / (d1 * x + d2)) + 0.5 * d2 * torch.log(d2 / (d1 * x + d2))
    log_beta = torch.lgamma(d1 / 2) + torch.lgamma(d2 / 2) - torch.lgamma((d1 + d2) / 2)
    log_denominator = torch.log(x) + log_beta
    return torch.exp(log_numerator - log_denominator)

  def F_cdf(self, F, d1, d2, n=150000000):
    x_values = torch.linspace(0, F, n + 1, device=self.device)+1e-7
    pdf_values = self.F_pdf(x_values, d1, d2)
    cdf_value = torch.trapz(pdf_values, x_values)
    return cdf_value

  def F_test(self, sample_1, sample_2, alpha=0.05, test_type="two-tail"):

    # Convert input to tensors of floating point numbers
    sample_1 = self.to_tensor(sample_1)
    sample_2 = self.to_tensor(sample_2)

    # Calculate standard deviations
    std1 = torch.std(sample_1, unbiased=True)
    std2 = torch.std(sample_2, unbiased=True)

    # calculate n, degrees of freedom and F-statistic
    n1 = len(sample_1)
    d1 =  n1 - 1
    n2 = len(sample_2)
    d2 =  n2 - 1

    # Ensure the larger variance is in the numerator
    if std1**2 > std2**2:
        f_statistic = (std1 ** 2) / (std2 ** 2)
    else:
        f_statistic = (std2 ** 2) / (std1 ** 2)
        # Swap degrees of freedom
        d1, d2 = d2, d1

    # Calculate the p-value
    if test_type == 'lower-tail':
        p_value = self.F_cdf(f_statistic, d1, d2)
    elif test_type == 'upper-tail':
        p_value = 1 - self.F_cdf(f_statistic, d1, d2)
    elif test_type == 'two-tail':
        left_tail = self.F_cdf(f_statistic, d1, d2)
        right_tail = 1 - self.F_cdf(f_statistic, d1, d2)
        p_value = 2 * min(left_tail, right_tail)
    else:
        raise ValueError('test_type must be "lower-tail", "upper-tail", or "two-tail"')

    # Determine whether to reject or fail to reject the null hypothesis
    if p_value < alpha:
        print('Reject the null hypothesis')
    else:
        print('Fail to reject the null hypothesis')

    return f_statistic, p_value

  def one_way_ANOVA(self, *samples, alpha=0.05):

    if len(samples) < 3:
      raise ValueError("one-way ANOVA should be used with 3 samples or more")

    # Ensure the input is a list of tensors
    if not all(isinstance(sample, torch.Tensor) for sample in samples):
        samples = [self.to_tensor(sample) for sample in samples]

    # Number of groups
    k = len(samples)

    # Total number of observations
    n = torch.sum(torch.tensor([len(sample) for sample in samples]))

    # Calculate the grand mean
    grand_mean = torch.sum(torch.stack([sample.sum() for sample in samples])) / n

    # Calculate the Between Group Variation (SSB)
    ssb = torch.sum(torch.stack([len(sample) * (sample.float().mean() - grand_mean) ** 2 for sample in samples]))

    # Calculate the Within Group Variation (SSW)
    ssw = torch.sum(torch.stack([((sample.float() - sample.float().mean()) ** 2).sum() for sample in samples]))


    # Degrees of Freedom
    df1 = k - 1
    df2 = n - k

    # Calculate the F-statistic and p-value
    f_statistic = (ssb / df1) / (ssw / df2)
    p_value = 1 - self.F_cdf(f_statistic, df1, df2)

    # Determine whether to reject or fail to reject the null hypothesis
    if p_value < alpha:

        print('Reject the null hypothesis')

        # Combine all groups into a single array and provide group labels
        data = np.concatenate(samples)
        labels = np.concatenate([[f'group_{i}'] * len(sample) for i, sample in enumerate(samples)])

        # Perform Tukey's HSD test
        tukey_result = pairwise_tukeyhsd(data, labels, alpha=alpha)
        print("Tukey's HSD Test Results:")
        print(tukey_result)

    else:
        print('Fail to reject the null hypothesis')

    return f_statistic, p_value

  def goodness_of_fit(self, expected, observed, alpha = 0.05):

    # Ensure the input expected and observed values are tensors with float values.
    if not torch.is_tensor(expected):
        expected = torch.tensor(expected, dtype=torch.float).to(self.device)
    else:
        expected = expected.float().to(self.device)

    if not torch.is_tensor(observed):
        observed = torch.tensor(observed, dtype=torch.float).to(self.device)
    else:
        observed = observed.float().to(self.device)

    # Number of elements in a sample and degrees of freedeom (df)
    n = len(expected)
    df = n - 1

    # calculate chi_square statistic
    chi_value = torch.sum((observed - expected)**2/expected)

    # calculate CDF p-value using chi-sqaure distribution using CDF for upper tail only:
    p_value = 1 - self.chi_cdf(chi_value, df)

    # Check the results of the hypothesis tests
    if p_value < alpha:
        print('Null hypothesis is rejected for the test')
    else:
        print('Null hypothesis is accepted for the test')

    return chi_value, p_value

  def chi_independence(self, observed, alpha = 0.05):

    # Ensure the input observed matrix is tensor with float values.
    if not torch.is_tensor(observed):
        observed = torch.tensor(observed, dtype=torch.float).to(self.device)
    else:
        observed = observed.float().to(self.device)

    # Sum across rows and columns
    row_sums = torch.sum(observed, dim=1)
    col_sums = torch.sum(observed, dim=0)
    grand_total = torch.sum(observed)

    # Expected frequencies
    expected = torch.outer(row_sums, col_sums) / grand_total

    # Calculate the Chi-Square statistic
    chi_value = torch.sum((observed - expected) ** 2 / expected)

    # n, m and degrees of freedom
    num_rows, num_cols = observed.shape
    df = (num_rows - 1) * (num_cols - 1)

    # calculate CDF p-value using chi-sqaure distribution's CDF for upper tail only
    p_value = 1 - self.chi_cdf(chi_value, df)

    # Check the results of the hypothesis tests
    if p_value < alpha:
        print('Null hypothesis is rejected for the test')
    else:
        print('Null hypothesis is accepted for the test')

    return chi_value, p_value
