import sys
import numpy
import scipy
import pyscf
import pyscf.dft
from qstack.spahm.LB2020guess import LB2020guess as LB20

def hcore(mol, *_):
  h  = mol.intor_symmetric('int1e_kin')
  h += mol.intor_symmetric('int1e_nuc')
  return h

def GWH(mol, *_):
  h = hcore(mol)
  S = mol.intor_symmetric('int1e_ovlp')
  K = 1.75 # See J. Chem. Phys. 1952, 20, 837
  h_gwh = numpy.zeros_like(h)
  for i in range(h.shape[0]):
    for j in range(h.shape[1]):
      if i != j:
        h_gwh[i,j] = 0.5 * K * (h[i,i] + h[j,j]) * S[i,j]
      else:
        h_gwh[i,j] = h[i,i]
  return h_gwh

def SAD(mol, func):
  hc = hcore(mol)
  dm =  pyscf.scf.hf.init_guess_by_atom(mol)
  mf = pyscf.dft.RKS(mol)
  mf.xc = func
  vhf = mf.get_veff(dm=dm)
  fock = hc + vhf
  return fock

def SAP(mol, *_):
  mf = pyscf.dft.RKS(mol)
  vsap = mf.get_vsap()
  t = mol.intor_symmetric('int1e_kin')
  fock = t + vsap
  return fock

def LB(mol, *_):
  return LB20(parameters='HF').Heff(mol)

def LB_HFS(mol, *_):
  return LB20(parameters='HFS').Heff(mol)

def solveF(mol, fock):
  s1e = mol.intor_symmetric('int1e_ovlp')
  return scipy.linalg.eigh(fock, s1e)

def get_guess(arg):
  arg = arg.lower()
  guesses = {'core':hcore, 'sad':SAD, 'sap':SAP, 'gwh':GWH, 'lb':LB, 'huckel':'huckel', 'lb-hfs':LB_HFS}
  if arg not in guesses.keys():
    print('Unknown guess. Available guesses:', list(guesses.keys()), file=sys.stderr);
    exit(1)
  return guesses[arg]

def get_occ(e, nelec, spin):
    if spin==None:
        nocc = nelec[0]
        return e[:nocc,...]
    else:
        nocc = nelec
        e1 = numpy.zeros((2, *e.shape))[:,:nocc[0],...]
        e1[0,:nocc[0],...] = e[:nocc[0],...]
        e1[1,:nocc[1],...] = e[:nocc[1],...]
        return e1

def get_dm(v, nelec, spin):
  if spin==None:
    nocc = nelec[0]
    dm = v[:,:nocc] @ v[:,:nocc].T
    return 2.0*dm
  else:
    nocc = nelec
    dm0 = v[:,:nocc[0]] @ v[:,:nocc[0]].T
    dm1 = v[:,:nocc[1]] @ v[:,:nocc[1]].T
    return numpy.array((dm0,dm1))

###############################################################################

def hcore_grad(mf):
    return mf.hcore_generator(mf.mol)

def LB_grad(mf):
    hcore_grad = mf.hcore_generator(mf.mol)
    HLB_grad   = LB20().HLB20_generator(mf.mol)
    def H_grad(iat):
        return hcore_grad(iat) + HLB_grad(iat)
    return H_grad

def get_guess_g(arg):
    arg = arg.lower()
    guesses = {'core':(hcore, hcore_grad), 'lb':(LB, LB_grad)}
    if arg not in guesses.keys():
        print('Unknown guess. Available guesses:', list(guesses.keys()), file=sys.stderr);
        exit(1)
    return guesses[arg]

def eigenvalue_grad(mol, e, c, s1, h1):

    """Compute gradients of eigenvalues found from HC=eSC

    Args:
        mol (pyscf Mole): pyscf Mole object
        e (numpy 1d ndarray, mol.nao): eigenvalues
        c (numpy 2d ndarray, mol.nao*mol.nao): eigenvectors
        s1 (numpy 3d ndarray, 3*mol.nao*mol.nao): compact gradient of the overlap matrix [-(nabla \|\)]
        h1 (func(int: iat)): returns the derivative of H wrt the coordinates of atom iat, i.e. dH/dr[iat]

    Returns:
        numpy 3d ndarray, mol.nao*mol.natm*3: gradient of the eigenvalues in Eh/bohr

    """
    de_dr = numpy.zeros((mol.nao, mol.natm, 3))
    aoslices = mol.aoslice_by_atom()[:,2:]
    for iat in range(mol.natm):
        dH_dr = h1(iat)
        p0, p1 = aoslices[iat]
        Hcomp = numpy.einsum('pi,aqp,qi->ia', c, dH_dr, c)
        Scomp = 2.0 * numpy.einsum('pi,aqp,qi->ia', c, s1[:,p0:p1], c[p0:p1])
        de_dr[:,iat,:] = Hcomp - Scomp * e[:,None]
    return de_dr
