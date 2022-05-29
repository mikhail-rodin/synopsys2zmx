import io
import os.path
from math import tan, radians
import itertools
import argparse

def pairwise(iterable):
    "s -> (s0, s1), (s1, s2), (s2, s3), ..."
    a, b = itertools.tee(iterable)
    next(b, None)
    return zip(a, b)   
def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

class SynObject:
    OBA = 1
    OBB = 2
    OBC = 3
    OBD = 4
    OBG = 5

class Surface:
    def __init__(self, cv=0, n=1, d=0, v=1, D=1, air=True, is_stop=False, d_infty=False):
        self.cv = cv
        self.n = n
        self.d = d
        self.v = v
        self.D = D
        self.air=air
        self.is_stop=is_stop
        self.d_infty=d_infty
    def rle(self):
        return f"CV {self.cv} TH {self.d}" + (" AIR" if self.air else f" GLM {self.n} {self.v}")
    def zmx(self):
        return f"""
        TYPE STANDARD
        CURV {self.cv} 1 0 0 0
        HIDE 0 0 0 0 0 0 0 0 0 0
        MIRR 2 0
        DISZ {self.d if not self.d_infty else 'INFINITY'}
        {f"GLAS ___BLANK 1 0 {self.n} {self.v} 5E-3 0 0 0 0 0" if not self.air else ''}
        DIAM {0.5*self.D} {int(self.is_stop)} 0 0 1 ""
        """
class Lens:
    def __init__(self, filepath):
        with io.open(filepath, "rt") as file:
            lines = file.readlines()
        self.w=0 # half field in deg
        # w>0 for y>0 (russian convention, opposite to OSD)
        self.sP=0 # entrance pupil positiion
        self.D=1 # entrance pupil diameter
        self.name='converted from RLE'
        self.surfaces=[Surface(), Surface()] # 0 and 1 reserved for obj & stop
        self.waves=[0.48613, 0.58756, 0.65627] 
        self.implied_stop=False
        self.stop_surf_i=-1
        self.ray_aiming=False
        self.obj_type=SynObject.OBB
        self._rleparse(lines)
    def _rleparse(self, lines):
        for line in lines:
            words = [w for w in line.split(' ') if w] # nonempty
            if words[0] == 'OBB':
                self.obj_type = SynObject.OBB
                self.w = -float(words[2])
                self.D = 2*float(words[3])
                YP1 = float(words[3]) # YP1 = -sP*tg(w)
                self.sP = -YP1/tan(radians(self.w))
            elif words[0] == 'ID':
                self.name = 'Synopsys ' + words[1] + ' LOG No=' + words[2]
            elif words[0] == 'WAVL':
                if not is_number(words[1]): continue
                self.waves = [float(w) for w in words[1:]]
            elif words[0] == 'APS':
                if len(words) > 1:
                    aps = int(words[1])
                    if aps < 0: self.ray_aiming = True
                    if aps == 1: 
                        self.implied_stop = True
                    else:
                        self.implied_stop = False
                        self.stop_surf_i = abs(aps)
            elif words[0].isdigit():
                # len([])=0, Synopsys surface indices are 0-based
                i = int(words[0]) + 2 # 0=obj, 1=stop
                if i >= len(self.surfaces) - 2: 
                    self.surfaces.append(Surface())
                srf = self.surfaces[i]
                srf.D = self.D # TODO: correct diam calculation
                if i == self.stop_surf_i:
                    srf.is_stop = True
                it = iter(pairwise(words))
                for word, nextword in it:
                    match word:
                        case 'RAD':
                            srf.cv = 1./float(nextword)
                        case 'CV':
                            srf.cv = float(nextword)
                        case 'TH':
                            srf.d = float(nextword)
                        case 'GLM':
                            srf.air = False
                            n, v = next(it, None)
                            srf.n = float(n)
                            srf.v = float(v)
                        case 'AIR':
                            srf.air = True
        if self.obj_type == SynObject.OBB:
            self.surfaces[0].d_infty=True
        if self.implied_stop:
            self.surfaces[1].d = self.sP
            self.surfaces[1].D = self.D
    def _zmx_sys(self, glasscat, zmx_version):
        sys = f"""
        VERS {zmx_version}
        MODE SEQ
        NAME {self.name}
        PFIL 0 0 0
        UNIT MM X W X CM MR CPMM
        {f'ENPD {self.D}' if self.implied_stop else ''}
        {'FLOA' if self.implied_stop else ''}
        ENVD 2.0E+1 1 0
        GFAC 0 0
        GCAT {glasscat}
        RAIM 0 {'2' if self.ray_aiming else '0'} 1 1 0 0 0 0 0
        SDMA 0 1 0
        FTYP 0 0 3 3 0 0 0
        ROPD 2
        PICB 1
        XFLN 0 0 0 0 0 0 0 0 0 0 0 0
        YFLN 0 {0.5*self.w} {0.7*self.w} {self.w} 0 0 0 0 0 0 0 0
        FWGN 1 1 1 1 1 1 1 1 1 1 1 1
        """
        for i, w in enumerate(self.waves):
            sys += f"WAVM {i+1} {w} 1\n"
        sys += """PWAV 2
        GLRS 1 0
        """
        return sys
    def zmx(self, zmx_version, glasscat='LZOS SCHOTT CDGM'):
        sys = self._zmx_sys(glasscat, zmx_version)
        surfs = ''
        for i, s in enumerate(self.surfaces):
            surfs += f"\nSURF {i}\n"
            surfs += s.zmx()
        return sys + surfs

ap = argparse.ArgumentParser(
    description="Synopsys RLE to Zemax ZMX file converter"
)
ap.add_argument(
    'rle_file',
    type=str,
    help='path to Synopsys RLE file'
)
ap.add_argument(
    '--zmx-version',
    '-v',
    type=str,
    required=True,
    dest='zmx_version',
    help='Zemax version string (string after VERS in a .zmx file)'
)
ap.add_argument(
    '--outputdir',
    '-o',
    type=str,
    dest='out',
    required=False,
    default='./'
)
ap.add_argument(
    "--name",
    "-n",
    type=str,
    required=False,
    dest='name',
    help="Name of .zmx file"
)
ap.add_argument(
    "--glasscat",
    '-g',
    required=False,
    type=str,
    default='SCHOTT CDGM',
    dest='glass',
    help="String of glass catalogs as in Zemax system options, e.g 'LZOS CDGM'"
)
args = ap.parse_args()

rle_path = os.path.normpath(args.rle_file)
rle_name = os.path.splitext(os.path.basename(rle_path))[0]
out_dir = os.path.normpath(args.out)
if not os.path.isdir(out_dir):
    print('ERROR: specified output dir cannot be found, likely does not exist')
    os._exit(1)
lens = Lens(rle_path)
zmx_name = rle_name if args.name is None else args.name
zmx_path = os.path.join(out_dir, f"{zmx_name}.zmx")
with io.open(zmx_path, 'w') as zmx_file:
    print(f"Saving {zmx_path}...")
    zmx_file.write(lens.zmx(args.zmx_version, args.glass))