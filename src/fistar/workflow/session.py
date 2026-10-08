from dataclasses import asdict, replace
from datetime import datetime
from uuid import uuid4
from fistar.core.models import *
from fistar.core.analysis import evaluate_spokes, evaluate_centroids

class AnalysisSession:
    steps=('image','identity','calibration','laser','spokes','result')
    def __init__(self):
        self.revision=0
        self.dirty=False
        self.image=None
        self.channel='luminance'
        self.device=''
        self.axis='gantry';self.axis_definition={}
        self.calibration=None
        self.calibration_mode='none'; self.calibration_error=''
        self._detection_inputs=None
        self.laser=None
        self.spokes=()
        self.detection=None
        self.detection_settings=None
        self.result=None
        self.center_method='intersection_centroid'
        self.analysis_at=None
        self.error=''
        self.confirmed_steps=set()
    def _change(self, step):
        self.revision+=1; self.dirty=self.image is not None
        self.confirmed_steps.difference_update(self.steps[self.steps.index(step):])
        self._evaluate()
    def _evaluate(self):
        self.result=None; self.error=''
        if self.laser and self.spokes:
            try:
                self.result=replace(evaluate_spokes(self.spokes,self.laser,self.calibration),center_method=self.center_method)
                self.analysis_at=datetime.now().astimezone().isoformat()
            except ValueError as e: self.error=str(e)
    def set_image(self,image):
        revision=self.revision;axis=self.axis
        self.__init__(); self.revision=revision;self.axis=axis
        self.image=image
        self.detection_settings=DetectionSettings()
        self._change('image')
    def set_identity(self,device,axis):
        if not axis: raise ValueError('回転軸を選択してください')
        device=device.strip()
        if (device,axis)==(self.device,self.axis): return
        self.device=device; self.axis=axis; self._change('identity')
    def set_channel(self,channel,discard_edits=False):
        if channel!='luminance': raise ValueError('解析は輝度固定です')
        if any(s.origin=='manual' for s in self.spokes) and not discard_edits:
            raise ValueError('チャンネル変更には手動修正を破棄する確認が必要です')
        self.channel=channel; self.spokes=(); self.detection=None; self._change('image')
    def set_calibration(self,calibration,mode=None,error=''):
        self.calibration_mode=mode or ('tag' if calibration and calibration.source=='TIFF' else 'manual' if calibration and calibration.reference else 'numeric' if calibration else 'none')
        self.calibration_error=error
        self.calibration=calibration; self._change('calibration')
    def set_laser(self,laser):
        if not self.image or not (0<=laser.x<self.image.raw.shape[1] and 0<=laser.y<self.image.raw.shape[0]):
            raise ValueError('画像内のレーザー点を指定してください')
        self.laser=laser; self._change('laser')
    def set_detection_settings(self,settings):
        if settings==self.detection_settings: return
        self.detection_settings=settings; self._change('spokes')
    def set_detection(self,detection,discard_edits=False):
        if any(s.origin=='manual' for s in self.spokes) and not discard_edits:
            raise ValueError('再検出には手動修正を破棄する確認が必要です')
        self.channel='luminance'
        self.detection=detection
        if isinstance(detection.settings,DetectionSettings): self.detection_settings=detection.settings
        self.spokes=detection.spokes; self._detection_inputs=self.detection_inputs
        self._change('spokes')
    def apply_detection(self,revision,image_hash,detection,discard_edits=False):
        if revision!=self.revision or not self.image or image_hash!=self.image.sha256: return False
        self.set_detection(detection,discard_edits); return True
    def replace_spoke(self,spoke):
        if any(s.id==spoke.id for s in self.spokes):
            self.spokes=tuple(spoke if s.id==spoke.id else s for s in self.spokes)
        else: self.spokes+= (spoke,)
        self._change('spokes')
    def set_center_method(self,method):
        if method not in ('minimax','intersection_centroid'): raise ValueError('中心推定方式が不正です')
        if method==self.center_method: return
        self.center_method=method
        self.revision+=1; self.dirty=self.image is not None; self.confirmed_steps.discard('result')
        if self.result:
            if method=='intersection_centroid' and self.result.centroid_pixels is None and not self.result.centroid_error:
                pixels,physical,error=evaluate_centroids(self.spokes,self.laser,self.calibration)
                self.result=replace(self.result,centroid_pixels=pixels,
                    centroid_physical=physical,centroid_error=error,
                    center_method=method)
            else: self.result=replace(self.result,center_method=method)
            self.analysis_at=datetime.now().astimezone().isoformat()

    def confirm_step(self,step):
        index=self.steps.index(step)
        if step=='result' and not self.ready_for_review: raise ValueError(self.readiness_message)
        if step=='image' and self.image is None: raise ValueError('画像を選択してください')
        if step=='result' and self.channel!='luminance': raise ValueError('旧記録の解析チャンネルを保持しています。輝度で再検出してから結果を確認してください')
        if step=='laser' and self.laser is None: raise ValueError('レーザー点を指定してください')
        if step in ('spokes','result') and (self.result is None or (step=='result' and self.result.selected is None)): raise ValueError(self.error or (self.result.centroid_error if self.result else '') or '有効な中心線が必要です')
        self.confirmed_steps.add(step); self.dirty=True
    @property
    def detection_inputs(self):
        return (self.image.sha256 if self.image else None,self.channel,self.laser,self.detection_settings)
    @property
    def requires_redetection(self):
        return self.detection is None or self._detection_inputs!=self.detection_inputs
    @property
    def can_detect(self):
        return self.image is not None and self.laser is not None and not self.calibration_error and (self.calibration_mode=='none' or self.calibration is not None)
    @property
    def readiness_message(self):
        if self.image is None: return '画像を開いてください'
        if self.calibration_error: return self.calibration_error
        if self.calibration_mode!='none' and self.calibration is None:return '選択した方法の校正を完了してください'
        if self.laser is None: return '基準点選択ボタンを押し、画像上でレーザー基準点を指定してください'
        if self.channel!='luminance': return '旧記録を輝度で再検出してください'
        if self.requires_redetection: return '再検出が必要です。レーザー位置と検出条件を確認し「照射帯を検出」を押してください'
        if self.result is None: return self.error or '有効な中心線が不足しています'
        if self.result.selected is None: return self.result.centroid_error or '選択方式を計算できません'
        return ''
    @property
    def ready_for_review(self):
        return not self.readiness_message
    @property
    def can_save(self):
        return self.ready_for_review and 'result' in self.confirmed_steps
    def snapshot(self):
        metadata=None
        if self.detection:
            d=self.detection
            metadata={'method':d.method,'pylinac_version':d.pylinac_version,
                      'settings':asdict(d.settings) if isinstance(d.settings,DetectionSettings) else dict(d.settings),
                      'points':[asdict(p) for p in d.points],
                      'search_center':asdict(d.search_center) if d.search_center else None,
                      'radius_px':d.radius_px,'warnings':list(d.warnings)}
        return {'schema_version':5,'laser_delta_y_positive':'up','axis_definition':self.axis_definition,'judgment_enabled':False,'calibration_mode':self.calibration_mode,'app_version':'1.2.0','algorithm_version':'fistar-1.2','center_method':self.center_method,
                'image_path':str(self.image.path) if self.image else None,
                'image_sha256':self.image.sha256 if self.image else None,
                'channel':self.channel,'channel_transform':'0.299R+0.587G+0.114B' if self.channel=='luminance' else self.channel,'calibration':asdict(self.calibration) if self.calibration else None,
                'laser':asdict(self.laser) if self.laser else None,
                'detection_settings':asdict(self.detection_settings) if self.detection_settings else None,
                'detection_metadata':metadata,
                'detected_spokes':[asdict(s) for s in self.detection.spokes] if self.detection else [],
                'spokes':[asdict(s) for s in self.spokes], 'confirmed_steps':sorted(self.confirmed_steps)}
    def measurement(self,limits=None):
        if not self.can_save: raise ValueError(self.readiness_message or '結果の確認後に保存できます')
        return Measurement(str(uuid4()),self.analysis_at,self.device,self.axis,
                           self.image.path.name,self.result,Limits(),Judgment('not_evaluated','not_evaluated'),self.snapshot())
    def restore(self,image,record):
        data=record.snapshot
        self.axis_definition=data.get("axis_definition",{})
        if image.sha256!=data['image_sha256']: raise ValueError('元画像が一致しません')
        self.set_image(image); self.device=record.device; self.axis=record.axis; self.channel=data['channel']
        c=data['calibration']
        if c:
            ref=c.get('reference')
            self.calibration=Calibration(c['sx_mm'],c['sy_mm'],c['source'],(Point(**ref[0]),Point(**ref[1]),ref[2]) if ref else None)
        else: self.calibration=None
        self.laser=Point(**data['laser'])
        old_settings=data.get('detection_settings')
        if old_settings and 'radius_ratio' in old_settings:
            self.detection_settings=DetectionSettings(**old_settings)
        else:
            # Legacy annulus/threshold values are not meaningful as circle/FWHM settings.
            self.detection_settings=DetectionSettings()
        def spoke(d):
            return Spoke(d['id'],Line(**d['line']),tuple(Point(**p) for p in d['support']),d['origin'],d['excluded'])
        self.spokes=tuple(spoke(d) for d in data['spokes'])
        metadata=data.get('detection_metadata')
        detected=tuple(spoke(d) for d in data.get('detected_spokes',[]))
        if metadata:
            settings=metadata['settings']
            if 'radius_ratio' in settings: settings=DetectionSettings(**settings)
            self.detection=DetectionResult(detected,settings,tuple(metadata.get('warnings',())),metadata['method'],
                metadata.get('pylinac_version'),tuple(Point(**p) for p in metadata.get('points',())),
                Point(**metadata['search_center']) if metadata.get('search_center') else None,metadata.get('radius_px'))
        elif old_settings and 'inner_radius_px' in old_settings:
            self.detection=DetectionResult(detected,dict(old_settings),method='legacy-threshold-tls')
        else:
            self.detection=None
        # Reopening displays the saved calculation; only an edit computes a new result.
        self.result=record.result
        self.center_method=record.result.center_method
        self.analysis_at=record.created_at
        self.calibration_mode=data.get('calibration_mode') or ('tag' if self.calibration and self.calibration.source=='TIFF' else 'manual' if self.calibration and self.calibration.reference else 'numeric' if self.calibration else 'none')
        self._detection_inputs=self.detection_inputs if self.detection else None
        self.confirmed_steps=set(); self.dirty=False
