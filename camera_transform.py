import cv2
import numpy as np
from PIL import Image

def apply_3d_rotation(pil_img, pitch=0, yaw=0, roll=0):
    if pitch == 0 and yaw == 0 and roll == 0:
        return pil_img
        
    img = np.array(pil_img.convert('RGB'))
    h, w = img.shape[:2]
    
    pad = int(max(w, h) * 1.5)  # generous padding to prevent clipping
    img_padded = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=[255, 255, 255])
    hp, wp = img_padded.shape[:2]
    
    cx, cy = wp / 2, hp / 2
    
    rx = np.radians(pitch)
    ry = np.radians(yaw)
    rz = np.radians(roll)
    
    Rx = np.array([[1, 0, 0, 0], [0, np.cos(rx), -np.sin(rx), 0], [0, np.sin(rx), np.cos(rx), 0], [0, 0, 0, 1]])
    Ry = np.array([[np.cos(ry), 0, np.sin(ry), 0], [0, 1, 0, 0], [-np.sin(ry), 0, np.cos(ry), 0], [0, 0, 0, 1]])
    Rz = np.array([[np.cos(rz), -np.sin(rz), 0, 0], [np.sin(rz), np.cos(rz), 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    R = Rx.dot(Ry).dot(Rz)
    
    f = max(w, h)  # focal length based on original (unpadded) size
    d = 2.5 * f  # push camera back so the image doesn't scale out of bounds
    
    T1 = np.array([[1,0,0,-cx], [0,1,0,-cy], [0,0,1,0], [0,0,0,1]])
    # don't re-add cx,cy here — the camera matrix P handles 2D centering
    T2 = np.array([[1,0,0,0], [0,1,0,0], [0,0,1,d], [0,0,0,1]])
    
    # using d as focal length keeps scale at 1x when Z=0
    P = np.array([[d, 0, cx, 0], [0, d, cy, 0], [0, 0, 1, 0]])
                  
    corners = np.array([[0,0,0,1], [wp,0,0,1], [wp,hp,0,1], [0,hp,0,1]]).T
    transformed = T2 @ R @ T1 @ corners
    proj = P @ transformed
    proj = proj / proj[2, :]
    dst_pts = proj[:2, :].T.astype(np.float32)
    src_pts = np.array([[0,0], [wp,0], [wp,hp], [0,hp]], dtype=np.float32)
    
    H = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(img_padded, H, (wp, hp), borderValue=(255,255,255))
    
    gray = cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 254, 255, cv2.THRESH_BINARY_INV)
    coords = cv2.findNonZero(thresh)
    if coords is not None:
        x, y, bw, bh = cv2.boundingRect(coords)
        x = max(0, x-30); y = max(0, y-30)
        bw = min(wp-x, bw+60); bh = min(hp-y, bh+60)
        warped = warped[y:y+bh, x:x+bw]
        
    return Image.fromarray(warped)

def apply_bend(pil_img, amount=0):
    if amount == 0:
        return pil_img
        
    img_np = np.array(pil_img.convert('RGB'))
    h, w = img_np.shape[:2]
    
    pad = int(max(w, h) * 0.2)
    img_padded = cv2.copyMakeBorder(img_np, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=[255, 255, 255])
    h, w = img_padded.shape[:2]
    
    y, x = np.indices((h, w), dtype=np.float32)
    
    theta_max = (amount / 100.0) * (np.pi / 2.5)
    
    map_x = x.copy()
    map_y = y.copy()
    
    if theta_max != 0:
        R = (w/2) / np.sin(abs(theta_max))
        apparent_x = x - w/2
        
        # clamp to [-1, 1] to avoid arcsin domain warnings
        theta = np.arcsin(np.clip(apparent_x / R, -1.0, 1.0))
        if amount < 0: theta = -theta
        
        orig_x = R * theta + w/2
        map_x = orig_x
        
        Z = R * (1 - np.cos(theta))
        if amount < 0: Z = -Z
        scale = R / (R + Z) 
        map_y = (y - h/2) / scale + h/2

    warped = cv2.remap(img_padded, map_x.astype(np.float32), map_y.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=[255,255,255])
    
    # auto-crop white borders
    gray = cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 254, 255, cv2.THRESH_BINARY_INV)
    coords = cv2.findNonZero(thresh)
    if coords is not None:
        cx, cy, cbw, cbh = cv2.boundingRect(coords)
        cx = max(0, cx-30); cy = max(0, cy-30)
        cbw = min(w-cx, cbw+60); cbh = min(h-cy, cbh+60)
        warped = warped[cy:cy+cbh, cx:cx+cbw]
        
    return Image.fromarray(warped)

def apply_wavy_bend(pil_img, amount=0):
    if amount == 0:
        return pil_img
        
    img_np = np.array(pil_img.convert('RGB'))
    h, w = img_np.shape[:2]
    
    pad = int(max(w, h) * 0.2)
    img_padded = cv2.copyMakeBorder(img_np, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=[255, 255, 255])
    h, w = img_padded.shape[:2]
    
    y, x = np.indices((h, w), dtype=np.float32)
    
    amplitude = (amount / 100.0) * (h * 0.05)
    freq = (2 * np.pi) / w * 2.5
    
    map_x = x.copy()
    map_y = y + amplitude * np.sin(x * freq)
    
    warped = cv2.remap(img_padded, map_x.astype(np.float32), map_y.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=[255,255,255])
    
    gray = cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 254, 255, cv2.THRESH_BINARY_INV)
    coords = cv2.findNonZero(thresh)
    if coords is not None:
        cx, cy, cbw, cbh = cv2.boundingRect(coords)
        cx = max(0, cx-30); cy = max(0, cy-30)
        cbw = min(w-cx, cbw+60); cbh = min(h-cy, cbh+60)
        warped = warped[cy:cy+cbh, cx:cx+cbw]
        
    return Image.fromarray(warped)
